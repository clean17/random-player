"""인물 중심 특징 추출 (2026-11-02). 2026-11-03부터 정리 화면 취향 모델의 입력(emb·emb_person·emb_face).

    venv_imgml/Scripts/python.exe tools/image_curate/features.py          # 증분
    venv_imgml/Scripts/python.exe tools/image_curate/features.py --full   # 전부 다시

사용자 기준(2026-11-02): 좋아하는 얼굴·몸의 라인·의상·포즈가 있고, 얼굴이 흐리거나 구도·포즈·몸의 태가 별로인 것을
뺀다. 범용 미적 점수(LAION aesthetic)는 이걸 못 본다(판정 기준 AUC 0.58). 그래서 이미지마다 아래를 뽑아 취향 모델의
입력으로 쓸 수 있는지 eval_features.py 로 먼저 검증한다.

  emb         전체 이미지 CLIP — ViT-L-14 **quickgelu**(openai 가중치의 원래 활성화. embed.py 는 quickgelu 없이
              불러와 값이 조금 어긋나 있다 — open_clip 경고) + 그 위의 aes(LAION aesthetic)
  emb_person  주 인물 영역 CLIP(몸의 라인·의상·포즈 — 배경 영향을 줄인다)
  emb_face    얼굴 영역 CLIP(얼굴 취향)
  scal        얼굴 선명도·크기, 인물 크기·위치·화면 밖 잘림, 인원 수, 관절 17개 좌표(인물 상자 기준 정규화) 등

검출: torchvision 공식 Keypoint R-CNN(COCO, PyTorch 배포 가중치). 얼굴 상자는 별도 얼굴 검출기 없이 관절 중
코·눈·귀 좌표로 잡는다(외부 개인 저장소의 얼굴 검출 가중치는 받지 않기로 함 — pickle 이라 코드 실행 위험).

캐시: cache/refine_feat.npz (embed.py 의 refine_clip.npz 와 별개). 정리 화면(app/image_curate.py)이 embed.py 다음에
이어서 자동 실행한다 — 바뀐/새 파일만 계산(약 14초, 대부분 모델 로딩). 판정 기록이 있는 이미지는 파일이 지워져도
남긴다(embed.py 와 같은 규칙, '_gone/<이름>').
"""
import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import cv2
import numpy as np
import torch
import torchvision
import open_clip
from PIL import Image, ImageFile

import json

from tools.image_curate.common import (CACHE_DIR, FEAT_PATH, GONE_PREFIX, LABELS_PATH, backup_file, base_name,
                                       list_images_recursive, list_images_with_review, resolve_ref_dir,
                                       utf8_stdout)
from tools.image_curate.embed import load_aesthetic

ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = None

MAX_SIDE = 2048          # 읽을 때 이 크기로 줄여 둔다(메모리). 얼굴 선명도는 이 해상도 기준
DET_SIDE = 1024          # 검출 입력 크기
PERSON_THR = 0.7         # 사람 검출 점수
KP_THR = 2.0             # 관절 점수(Keypoint R-CNN 히트맵 로짓) — 이보다 크면 보인다고 본다
FACE_KP = (0, 1, 2, 3, 4)   # 코, 왼눈, 오른눈, 왼귀, 오른귀

KP_NAMES = ['nose', 'leye', 'reye', 'lear', 'rear', 'lsho', 'rsho', 'lelb', 'relb', 'lwri', 'rwri',
            'lhip', 'rhip', 'lknee', 'rknee', 'lank', 'rank']
SCAL_COLS = (['has_person', 'n_persons', 'person_score', 'person_area', 'person_cx', 'person_cy', 'person_h',
              'cut_top', 'cut_bottom', 'cut_left', 'cut_right', 'person_sharp',
              'has_face', 'face_size', 'face_sharp', 'face_cx', 'face_cy', 'n_kp_vis', 'img_aspect']
             + ['kp_%s_%s' % (k, a) for k in KP_NAMES for a in ('x', 'y', 'v')])


def _load(path: str) -> Optional[Image.Image]:
    try:
        with Image.open(path) as im:
            im.seek(0)
            im = im.convert('RGB')
            w, h = im.size
            s = MAX_SIDE / max(w, h)
            if s < 1:
                im = im.resize((max(1, round(w * s)), max(1, round(h * s))), Image.BILINEAR)
            return im
    except Exception as e:  # noqa: BLE001
        print('  [skip] %s: %s' % (os.path.basename(path), e))
        return None


def _sharp(im: Image.Image, side: int) -> float:
    """선명도 = 일정 크기로 맞춘 회색조의 라플라시안 분산(log). 원래 작은 얼굴은 키우면서 흐려져 낮게 나온다."""
    g = np.asarray(im.convert('L').resize((side, side), Image.BILINEAR), dtype=np.float32)
    return float(np.log1p(cv2.Laplacian(g, cv2.CV_32F).var()))


def _face_box(kp: np.ndarray, ks: np.ndarray) -> Optional[Tuple[float, float, float]]:
    """관절(코·눈·귀)로 얼굴 정사각형 (cx, cy, size). 못 잡으면 None."""
    vis = {i: kp[i, :2] for i in FACE_KP if ks[i] > KP_THR}
    if len(vis) < 2:
        return None
    size = 0.0
    if 1 in vis and 2 in vis:
        size = max(size, np.linalg.norm(vis[1] - vis[2]) * 2.8)
    if 3 in vis and 4 in vis:
        size = max(size, np.linalg.norm(vis[3] - vis[4]) * 1.3)
    if size == 0.0 and 0 in vis:
        others = [vis[i] for i in (1, 2, 3, 4) if i in vis]
        if others:
            size = max(np.linalg.norm(vis[0] - p) for p in others) * 3.2
    if size < 16:
        return None
    pts = np.array([vis[i] for i in (0, 1, 2) if i in vis] or list(vis.values()))
    cx, cy = pts.mean(axis=0)
    return float(cx), float(cy + 0.12 * size), float(size)


def _crop(im: Image.Image, x0: float, y0: float, x1: float, y1: float) -> Image.Image:
    w, h = im.size
    return im.crop((max(0, int(x0)), max(0, int(y0)), min(w, int(round(x1))), min(h, int(round(y1)))))


def analyze(im: Image.Image, det: Dict) -> Tuple[np.ndarray, Optional[Image.Image], Optional[Image.Image]]:
    """검출 결과(det: 원본 좌표) → (scal 벡터, 인물 crop, 얼굴 crop)."""
    W, H = im.size
    s = np.zeros(len(SCAL_COLS), dtype=np.float32)
    col = {c: i for i, c in enumerate(SCAL_COLS)}
    s[col['img_aspect']] = W / H
    keep = det['scores'] >= PERSON_THR
    boxes, kps, kss, scores = det['boxes'][keep], det['keypoints'][keep], det['keypoints_scores'][keep], det['scores'][keep]
    s[col['n_persons']] = len(boxes)
    if not len(boxes):
        return s, None, None
    area = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    j = int(np.argmax(area * scores))
    x0, y0, x1, y1 = boxes[j]
    kp, ks = kps[j], kss[j]
    bw, bh = max(1.0, x1 - x0), max(1.0, y1 - y0)
    s[col['has_person']] = 1
    s[col['person_score']] = scores[j]
    s[col['person_area']] = area[j] / (W * H)
    s[col['person_cx']] = (x0 + x1) / 2 / W
    s[col['person_cy']] = (y0 + y1) / 2 / H
    s[col['person_h']] = bh / H
    m = 0.01
    s[col['cut_top']] = float(y0 <= m * H)
    s[col['cut_bottom']] = float(y1 >= (1 - m) * H)
    s[col['cut_left']] = float(x0 <= m * W)
    s[col['cut_right']] = float(x1 >= (1 - m) * W)
    vis = ks > KP_THR
    s[col['n_kp_vis']] = vis.sum()
    for k, name in enumerate(KP_NAMES):
        if vis[k]:
            s[col['kp_%s_x' % name]] = (kp[k, 0] - x0) / bw
            s[col['kp_%s_y' % name]] = (kp[k, 1] - y0) / bh
            s[col['kp_%s_v' % name]] = 1
    pad = 0.04
    pc = _crop(im, x0 - pad * bw, y0 - pad * bh, x1 + pad * bw, y1 + pad * bh)
    s[col['person_sharp']] = _sharp(pc, 256)
    fc = None
    fb = _face_box(kp, ks)
    if fb is not None:
        cx, cy, sz = fb
        fc = _crop(im, cx - sz / 2, cy - sz / 2, cx + sz / 2, cy + sz / 2)
        if min(fc.size) >= 8:
            s[col['has_face']] = 1
            s[col['face_size']] = sz / min(W, H)
            s[col['face_sharp']] = _sharp(fc, 112)
            s[col['face_cx']] = cx / W
            s[col['face_cy']] = cy / H
        else:
            fc = None
    return s, pc, fc


def main() -> None:
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default=None)
    ap.add_argument('--full', action='store_true')
    ap.add_argument('--batch', type=int, default=8)
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--limit', type=int, default=0, help='시험용: 처음 N장만')
    # 2026-11-03 다른 갤러리(image2 등) 1차 분류용 — 하위 폴더까지, 별도 캐시 파일에, 판정 기록과 무관하게
    ap.add_argument('--out', default=None, help='캐시 파일(생략 시 refine 캐시). 지정하면 --recursive 와 함께 쓴다')
    ap.add_argument('--recursive', action='store_true', help='하위 폴더까지(thumb/origin 제외), 이름=상대경로')
    args = ap.parse_args()
    out_path = args.out or FEAT_PATH
    key = (lambda n: n) if args.recursive else base_name    # 하위 폴더는 계정이 달라 파일명이 겹칠 수 있다

    ref_dir = resolve_ref_dir(args.dir)
    files = list_images_recursive(ref_dir) if args.recursive else list_images_with_review(ref_dir)
    if args.limit:
        files = files[:args.limit]
    print('대상:', ref_dir, '/ 이미지', len(files), '(하위 폴더 포함)' if args.recursive else '(보관함 포함)')

    old = None
    if not args.full and os.path.exists(out_path):
        with np.load(out_path, allow_pickle=False) as z:
            old = {k: z[k] for k in z.files}
        if list(old.get('scal_cols', [])) != SCAL_COLS:
            print('특징 구성이 바뀌어 전부 다시 계산')
            old = None
    reuse = {}
    if old is not None:
        for i, (n, sz, mt) in enumerate(zip(old['names'], old['sizes'], old['mtimes'])):
            reuse[key(str(n))] = (int(sz), float(mt), i)

    def cached(f):
        r = reuse.get(key(f[0]))
        return r is not None and r[0] == f[1] and abs(r[1] - f[2]) < 1e-3

    todo = [f for f in files if not cached(f)]
    print('재사용', len(files) - len(todo), '/ 새로 계산', len(todo))

    new = {}
    if todo:
        dev = 'cuda' if torch.cuda.is_available() else 'cpu'
        clip, _, prep = open_clip.create_model_and_transforms('ViT-L-14-quickgelu', pretrained='openai')
        clip = clip.to(dev).eval().half() if dev == 'cuda' else clip.to(dev).eval()
        aes_m = load_aesthetic(dev)
        W = torchvision.models.detection.KeypointRCNN_ResNet50_FPN_Weights.COCO_V1
        # 기본(min_size 800)은 입력을 800px 로 다시 키워 느리다(0.2초/장). 640 + fp16 이면 4배 빠르고 검출 수는 거의 같다
        det_m = torchvision.models.detection.keypointrcnn_resnet50_fpn(
            weights=W, box_score_thresh=0.5, min_size=640, max_size=DET_SIDE).to(dev).eval()
        tt = torchvision.transforms.functional.to_tensor

        def enc(ims: List[Image.Image]) -> np.ndarray:
            x = torch.stack([prep(i) for i in ims]).to(dev)
            if dev == 'cuda':
                x = x.half()
            with torch.no_grad():
                e = clip.encode_image(x).float()
            return (e / e.norm(dim=-1, keepdim=True)).cpu().numpy()

        pool = ThreadPoolExecutor(max_workers=args.workers)
        t0, done = time.time(), 0
        for b in range(0, len(todo), args.batch):
            chunk = todo[b:b + args.batch]
            ims = list(pool.map(lambda f: _load(os.path.join(ref_dir, f[0])), chunk))
            ok = [(f[0], im) for f, im in zip(chunk, ims) if im is not None]
            if ok:
                # 검출(줄인 이미지) → 원본(MAX_SIDE) 좌표로 되돌림
                xs, scales = [], []
                for _, im in ok:
                    sc = min(1.0, DET_SIDE / max(im.size))
                    sm = im if sc == 1.0 else im.resize((round(im.width * sc), round(im.height * sc)), Image.BILINEAR)
                    xs.append(tt(sm).to(dev)); scales.append(sc)
                with torch.no_grad(), torch.autocast(dev, dtype=torch.float16, enabled=(dev == 'cuda')):
                    outs = det_m(xs)
                rows = []
                for (n, im), o, sc in zip(ok, outs, scales):
                    d = {k: o[k].float().cpu().numpy() for k in ('boxes', 'scores', 'keypoints', 'keypoints_scores')}
                    d['boxes'] = d['boxes'] / sc
                    d['keypoints'][..., :2] = d['keypoints'][..., :2] / sc
                    rows.append((n, im) + analyze(im, d))
                e_full = enc([r[1] for r in rows])
                with torch.no_grad():
                    a_full = aes_m(torch.from_numpy(e_full).to(dev)).squeeze(-1).cpu().numpy()
                pi = [k for k, r in enumerate(rows) if r[3] is not None]
                fi = [k for k, r in enumerate(rows) if r[4] is not None]
                e_p = enc([rows[k][3] for k in pi]) if pi else None
                e_f = enc([rows[k][4] for k in fi]) if fi else None
                z = np.zeros(768, np.float32)
                for k, r in enumerate(rows):
                    new[r[0]] = (e_full[k], float(a_full[k]),
                                 e_p[pi.index(k)] if k in pi else z, e_f[fi.index(k)] if k in fi else z, r[2])
            done += len(chunk)
            if (b // args.batch) % 10 == 0 or done == len(todo):
                el = time.time() - t0
                print('  %d/%d  %.0fs  (%.1f장/s)' % (done, len(todo), el, done / max(el, 1e-6)), flush=True)
        pool.shutdown()

    names, sizes, mtimes, E, A, P, F, S = [], [], [], [], [], [], [], []
    todo_names = set(t[0] for t in todo)
    for n, sz, mt in files:
        if n in new:
            e, a, p, f, s = new[n]
        elif old is not None and n not in todo_names:
            i = reuse[key(n)][2]
            e, a, p, f, s = old['emb'][i], old['aes'][i], old['emb_person'][i], old['emb_face'][i], old['scal'][i]
        else:
            continue
        names.append(n); sizes.append(sz); mtimes.append(mt)
        E.append(e); A.append(a); P.append(p); F.append(f); S.append(s)

    # 판정 기록이 있는 이미지는 파일이 지워져도 특징을 남긴다 — 취향 모델의 학습 데이터(embed.py 와 같은 규칙)
    try:
        with open(LABELS_PATH, 'r', encoding='utf-8') as fh:
            labeled = set(n for n, v in json.load(fh).items() if v.get('src') != 'dup')   # 중복 정리 판정은 학습에 안 씀
    except (OSError, ValueError):
        labeled = set()
    if old is not None and labeled and not args.out:   # 다른 갤러리 캐시는 판정 기록과 무관
        present = set(base_name(n) for n in names)
        for i, on in enumerate(old['names']):
            b = base_name(str(on))
            if b in labeled and b not in present:
                names.append(GONE_PREFIX + '/' + b); sizes.append(int(old['sizes'][i])); mtimes.append(float(old['mtimes'][i]))
                E.append(old['emb'][i]); A.append(old['aes'][i]); P.append(old['emb_person'][i])
                F.append(old['emb_face'][i]); S.append(old['scal'][i])
                present.add(b)
    if not new and old is not None and [str(n) for n in old['names']] == names:
        print('변경 없음 — 캐시 그대로')
        return
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = out_path + '.tmp.npz'
    np.savez(tmp, names=np.array(names, dtype=str), sizes=np.array(sizes, np.int64), mtimes=np.array(mtimes, np.float64),
             emb=np.stack(E).astype(np.float16), aes=np.array(A, np.float32),
             emb_person=np.stack(P).astype(np.float16), emb_face=np.stack(F).astype(np.float16),
             scal=np.stack(S).astype(np.float32), scal_cols=np.array(SCAL_COLS, dtype=str))
    os.replace(tmp, out_path)
    if not args.out:
        backup_file(FEAT_PATH, 5)    # 다른 갤러리 캐시는 다시 만들 수 있어 백업하지 않는다
    S = np.stack(S)
    print('저장:', len(names), '건 ->', out_path)
    print('인물 검출 %.1f%% · 얼굴 %.1f%%' % (100 * S[:, 0].mean(), 100 * S[:, SCAL_COLS.index('has_face')].mean()))


if __name__ == '__main__':
    main()
