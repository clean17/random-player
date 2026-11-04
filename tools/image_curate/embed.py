"""refine 이미지의 CLIP 임베딩 + 미적 점수를 계산해 캐시한다 (1단계).

    venv_imgml/Scripts/python.exe tools/image_curate/embed.py            # 증분(바뀐/새 파일만)
    venv_imgml/Scripts/python.exe tools/image_curate/embed.py --full     # 전부 다시

- 별도 venv(venv_imgml, Python 3.12 + torch cu124) 전용. 자동매매가 쓰는 venv 에 torch 를 넣지 않으려고 분리했다.
- 파일을 읽기만 한다. 옮기거나 지우지 않는다.
- 모델: open_clip ViT-L-14 / openai 가중치. LAION aesthetic predictor 가 이 임베딩(768d) 위에서 학습된 것이라
  모델을 바꾸면 미적 점수를 못 쓴다.
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
import torch
import torch.nn as nn
import open_clip
from PIL import Image, ImageFile

from tools.image_curate.common import (CACHE_DIR, GONE_PREFIX, LABELS_PATH, base_name, list_images_with_review,
                                       load_cache, resolve_ref_dir, save_cache, utf8_stdout)

ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = None

AES_URL = ('https://github.com/christophschuhmann/improved-aesthetic-predictor/raw/main/'
           'sac+logos+ava1-l14-linearMSE.pth')
AES_PATH = os.path.join(CACHE_DIR, 'sac+logos+ava1-l14-linearMSE.pth')


class AestheticMLP(nn.Module):
    """improved-aesthetic-predictor 구조 그대로(state_dict 키 'layers.N.*' 와 맞아야 한다)."""

    def __init__(self, dim: int = 768):
        super().__init__()
        self.layers = nn.Sequential(
            nn.Linear(dim, 1024), nn.Dropout(0.2),
            nn.Linear(1024, 128), nn.Dropout(0.2),
            nn.Linear(128, 64), nn.Dropout(0.1),
            nn.Linear(64, 16),
            nn.Linear(16, 1),
        )

    def forward(self, x):
        return self.layers(x)


def load_aesthetic(device: str) -> AestheticMLP:
    if not os.path.exists(AES_PATH):
        os.makedirs(CACHE_DIR, exist_ok=True)
        print('aesthetic 가중치 다운로드:', AES_URL)
        urllib.request.urlretrieve(AES_URL, AES_PATH + '.part')
        os.replace(AES_PATH + '.part', AES_PATH)
    m = AestheticMLP()
    m.load_state_dict(torch.load(AES_PATH, map_location='cpu', weights_only=True))
    return m.to(device).eval()


def _open(path: str, preprocess) -> Optional[torch.Tensor]:
    try:
        with Image.open(path) as im:
            im.seek(0)  # gif 는 첫 프레임
            im = im.convert('RGB')
            return preprocess(im)
    except Exception as e:
        print('  [skip] %s: %s' % (os.path.basename(path), e))
        return None


def main() -> None:
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default=None, help='refine 경로(생략 시 설정에서 읽음)')
    ap.add_argument('--full', action='store_true', help='캐시 무시하고 전부 다시 계산')
    ap.add_argument('--batch', type=int, default=64)
    ap.add_argument('--workers', type=int, default=8, help='이미지 읽기/디코딩 스레드 수')
    args = ap.parse_args()

    ref_dir = resolve_ref_dir(args.dir)
    files = list_images_with_review(ref_dir)
    print('refine:', ref_dir, '/ 이미지', len(files), '(보관함 포함)')

    # 캐시에서 파일명·크기·mtime 이 같은 항목은 재사용(refine ↔ _review 이동은 이름만 바뀌므로 파일명 기준)
    old = None if args.full else load_cache()
    reuse = {}
    if old is not None:
        for i, (n, s, m) in enumerate(zip(old['names'], old['sizes'], old['mtimes'])):
            reuse[base_name(str(n))] = (int(s), float(m), i)

    def cached(f):
        r = reuse.get(base_name(f[0]))
        return r is not None and r[0] == f[1] and abs(r[1] - f[2]) < 1e-3

    todo = [f for f in files if not cached(f)]
    print('재사용', len(files) - len(todo), '/ 새로 계산', len(todo))

    new_emb = {}   # name -> (emb, aes)
    if todo:
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print('device:', device)
        model, _, preprocess = open_clip.create_model_and_transforms('ViT-L-14', pretrained='openai')
        model = model.to(device).eval()
        if device == 'cuda':
            model = model.half()
        aes_model = load_aesthetic(device)

        t0 = time.time()
        done = 0
        pool = ThreadPoolExecutor(max_workers=args.workers)
        for b in range(0, len(todo), args.batch):
            chunk = todo[b:b + args.batch]
            tensors = list(pool.map(lambda f: _open(os.path.join(ref_dir, f[0]), preprocess), chunk))
            ok: List[Tuple[str, torch.Tensor]] = [(f[0], t) for f, t in zip(chunk, tensors) if t is not None]
            if ok:
                x = torch.stack([t for _, t in ok]).to(device)
                if device == 'cuda':
                    x = x.half()
                with torch.no_grad():
                    e = model.encode_image(x).float()
                    e = e / e.norm(dim=-1, keepdim=True)
                    a = aes_model(e).squeeze(-1)
                e_np = e.cpu().numpy().astype(np.float16)
                a_np = a.cpu().numpy().astype(np.float32)
                for (n, _), ev, av in zip(ok, e_np, a_np):
                    new_emb[n] = (ev, av)
            done += len(chunk)
            el = time.time() - t0
            print('  %d/%d  %.0fs  (%.1f장/s)' % (done, len(todo), el, done / max(el, 1e-6)), flush=True)
        pool.shutdown()

    # 현재 파일 목록 순서로 캐시 재구성(사라진 파일은 자연히 빠진다)
    todo_names = set(t[0] for t in todo)
    names, sizes, mtimes, embs, aess = [], [], [], [], []
    for n, s, m in files:
        if n in new_emb:
            ev, av = new_emb[n]
        elif old is not None and n not in todo_names:
            i = reuse[base_name(n)][2]
            ev, av = old['emb'][i], old['aes'][i]
        else:
            continue  # 읽기 실패
        names.append(n); sizes.append(s); mtimes.append(m); embs.append(ev); aess.append(av)

    # 판정 기록이 있는 이미지는 파일이 지워져도(_review 를 비워도) 임베딩을 남긴다 — 취향 모델의 학습 데이터라서.
    # 지금 있는 파일과 이름이 겹치면 지금 파일이 우선(같은 이름의 다른 이미지일 수 있다).
    labeled = set()
    try:
        with open(LABELS_PATH, 'r', encoding='utf-8') as f:
            # 중복 정리(src=dup) 판정은 취향 학습에 안 쓴다 — 파일이 빠지면(보관함 '중복 제거분 정리') 캐시에서도 뺀다
            labeled = set(n for n, v in json.load(f).items() if v.get('src') != 'dup')
    except (OSError, ValueError):
        pass
    kept_gone = 0
    if old is not None and labeled:
        present = set(base_name(n) for n in names)
        for i, on in enumerate(old['names']):
            b = base_name(str(on))
            if b in labeled and b not in present:
                names.append(GONE_PREFIX + '/' + b); sizes.append(int(old['sizes'][i]))
                mtimes.append(float(old['mtimes'][i])); embs.append(old['emb'][i]); aess.append(old['aes'][i])
                present.add(b)
                kept_gone += 1
    if kept_gone:
        print('파일은 없지만 판정 기록이 있어 임베딩 유지:', kept_gone)

    # 바뀐 게 없으면 캐시를 다시 쓰지 않는다 — 정리 화면(app/image_curate.py)이 화면 열 때마다 이 스크립트를 띄우는데,
    # 매번 저장하면 캐시 mtime 이 바뀌어 점수 전체 재계산·'임베딩 갱신됨' 알림이 쓸데없이 일어난다.
    if (not new_emb and old is not None and len(names) == len(old['names'])
            and [str(n) for n in old['names']] == names
            and np.array_equal(old['sizes'], np.array(sizes, dtype=np.int64))
            and np.allclose(old['mtimes'], np.array(mtimes, dtype=np.float64), atol=1e-3)):
        print('변경 없음 — 캐시 그대로')
        return

    save_cache({
        'names': np.array(names, dtype=str),
        'sizes': np.array(sizes, dtype=np.int64),
        'mtimes': np.array(mtimes, dtype=np.float64),
        'emb': np.stack(embs).astype(np.float16) if embs else np.zeros((0, 768), np.float16),
        'aes': np.array(aess, dtype=np.float32),
    })
    print('저장:', len(names), '건 ->', os.path.relpath(os.path.join(CACHE_DIR, 'refine_clip.npz')))


if __name__ == '__main__':
    main()
