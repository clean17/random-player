"""image_curate 공통 — 경로·캐시 입출력. numpy 만 쓴다(Flask venv 와 ML venv 양쪽에서 import).

캐시(cache/refine_clip.npz) 구성:
  names  (N,)  str      refine 최상위 파일명
  sizes  (N,)  int64    파일 크기 — 크기/mtime 이 바뀌면 다시 계산
  mtimes (N,)  float64
  emb    (N,768) float16  CLIP ViT-L/14(openai) 이미지 임베딩, L2 정규화됨
  aes    (N,)  float32  LAION improved-aesthetic-predictor 점수(대략 1~10)
"""
import os
import subprocess
import sys
from typing import Dict, Optional

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
CACHE_DIR = os.path.join(HERE, 'cache')
CACHE_PATH = os.path.join(CACHE_DIR, 'refine_clip.npz')
# features.py 결과(전체·인물·얼굴 CLIP + 관절 등). 2026-11-03부터 정리 화면 취향 모델의 입력 — scoring.model_input
FEAT_PATH = os.path.join(CACHE_DIR, 'refine_feat.npz')
REVIEW_SUBDIR = '_review'   # 임시 보관함: 후보·중복 탭에서 제거한 이미지가 오는 refine 하위 폴더(최종 삭제 없음)
ARCHIVE_SUBDIR = '_archive' # 보관함: 임시 보관함에서 마지막 검토 후 넘긴 곳(2026-11-03). 판정·학습은 그대로
GONE_PREFIX = '_gone'       # 파일은 지워졌지만 판정 기록이 있어 임베딩만 남겨 둔 항목('_gone/<이름>')
LABELS_PATH = os.path.join(PROJECT_ROOT, 'logs', 'image_curate', 'labels.json')

IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.jfif', '.bmp')


def resolve_ref_dir(cli_dir: Optional[str]) -> str:
    """refine 경로. 설정이 DB(configs 테이블)에 있어 psycopg 가 있는 메인 venv 로 물어본다."""
    if cli_dir:
        return cli_dir
    try:
        from config.config import settings  # 메인 venv 에서 실행 중이면 바로 된다
        return settings['REF_IMAGE_DIR']
    except Exception:
        pass
    py = os.path.join(PROJECT_ROOT, 'venv', 'Scripts', 'python.exe')
    out = subprocess.run(
        [py, '-c', "import sys; sys.stdout.reconfigure(encoding='utf-8'); "
                   "from config.config import settings; print(settings['REF_IMAGE_DIR'])"],
        cwd=PROJECT_ROOT, capture_output=True, encoding='utf-8', check=True)
    d = out.stdout.strip().splitlines()[-1]
    if not os.path.isdir(d):
        raise SystemExit('refine 경로를 찾을 수 없음: %r (--dir 로 지정)' % d)
    return d


def list_images(ref_dir: str):
    """refine 갤러리와 같은 기준 — 최상위 파일만(origin/ thumb/ _review/ 제외)."""
    out = []
    for e in os.scandir(ref_dir):
        if e.is_file() and e.name.lower().endswith(IMAGE_EXTS):
            st = e.stat()
            out.append((e.name, st.st_size, st.st_mtime))
    out.sort(key=lambda x: x[0].lower())
    return out


def list_images_with_review(ref_dir: str):
    """refine 최상위 + 임시 보관함(_review/) + 보관함(_archive/). '<하위폴더>/<이름>' 으로 — 제거 판정 이미지의
    임베딩을 캐시에 남겨 둬야 취향 모델이 계속 학습에 쓸 수 있다."""
    out = list_images(ref_dir)
    for sub in (REVIEW_SUBDIR, ARCHIVE_SUBDIR):
        rv = os.path.join(ref_dir, sub)
        if os.path.isdir(rv):
            out += [(sub + '/' + n, s, m) for n, s, m in list_images(rv)]
    return out


def list_images_recursive(base: str):
    """하위 폴더까지(thumb/ origin/ 제외) — image2(인스타 계정별 폴더) 1차 분류용. 이름은 base 기준 상대경로('/')."""
    out = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in ('thumb', 'origin')]
        for f in files:
            if f.lower().endswith(IMAGE_EXTS) and not f.lower().endswith('.gif'):
                p = os.path.join(root, f)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                out.append((os.path.relpath(p, base).replace(os.sep, '/'), st.st_size, st.st_mtime))
    out.sort(key=lambda x: x[0].lower())
    return out


def base_name(cache_name: str) -> str:
    """캐시 이름('x.jpg' 또는 '_review/x.jpg') → 파일명. 이동해도 같은 파일로 본다."""
    return cache_name.rsplit('/', 1)[-1]


def load_cache() -> Optional[Dict[str, np.ndarray]]:
    if not os.path.exists(CACHE_PATH):
        return None
    with np.load(CACHE_PATH, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def load_feat() -> Optional[Dict[str, np.ndarray]]:
    """features.py 캐시. 없거나 읽다 실패하면 None(정리 화면은 전체 이미지 임베딩만으로 계속 동작)."""
    if not os.path.exists(FEAT_PATH):
        return None
    try:
        with np.load(FEAT_PATH, allow_pickle=False) as z:
            return {k: z[k] for k in ('names', 'emb', 'emb_person', 'emb_face')}
    except (OSError, ValueError, KeyError):
        return None


def save_cache(data: Dict[str, np.ndarray]) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = CACHE_PATH + '.tmp.npz'
    np.savez(tmp, **data)
    os.replace(tmp, CACHE_PATH)
    backup_file(CACHE_PATH, CACHE_BACKUP_KEEP)


# ── 자동 백업 (2026-11-02) ────────────────────────────────────────────────────
# labels.json(판정 기록)과 refine_clip.npz(임베딩)는 _review 를 비운 뒤엔 다시 만들 수 없는 학습 데이터다.
# 둘 다 gitignore 대상이라, 저장할 때마다 다른 물리 디스크(F:, C: 와 별개 SSD)에 시점별 사본을 남긴다.
# 내용이 직전 사본과 같으면 건너뛴다. 백업 실패는 경고만 하고 본 작업은 막지 않는다(F: 가 빠져 있어도 동작).
# 복구: 원하는 사본을 원래 이름(logs/image_curate/labels.json, tools/image_curate/cache/refine_clip.npz)으로 복사.
BACKUP_DIR = r'F:\image_curate_backup'
LABELS_BACKUP_KEEP = 50     # 확정할 때마다 생김(수 KB~수백 KB)
CACHE_BACKUP_KEEP = 10      # embed.py 실행할 때마다 생김(약 11MB)

# 보관함(_review)에서 '중복 제거분 정리'로 빼낸 파일 (2026-11-03 사용자 결정 — 영구 삭제 대신 F: 로 옮겨 보관,
# 필요 없으면 사용자가 폴더째 직접 지운다. refine 이 WSL UNC 경로라 휴지통이 동작하지 않는다).
# 구조: TRASH_DIR/dup_YYYYmmdd_HHMMSS/<파일>, 자르기 원본 백업은 .../origin/<파일>
# 다른 갤러리 1차 분류(2026-11-03, dir=image2)용 특징 캐시 — 다시 만들 수 있어 백업하지 않는다
SCREEN_FEAT_PATH = os.path.join(CACHE_DIR, 'image2_feat.npz')
TRASH_DIR = r'F:\image_curate_trash'


def _sha256(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def backup_file(path: str, keep: int) -> Optional[str]:
    """path 를 BACKUP_DIR/<파일명>/<이름>_YYYYmmdd_HHMMSS<확장자> 로 복사하고 오래된 사본을 keep 개만 남긴다."""
    import shutil
    import time as _time
    try:
        if not os.path.isfile(path):
            return None
        stem, ext = os.path.splitext(os.path.basename(path))
        d = os.path.join(BACKUP_DIR, stem + ext)
        os.makedirs(d, exist_ok=True)
        olds = sorted(f for f in os.listdir(d) if f.startswith(stem + '_') and f.endswith(ext))
        if olds and _sha256(os.path.join(d, olds[-1])) == _sha256(path):
            return None
        dst = os.path.join(d, '%s_%s%s' % (stem, _time.strftime('%Y%m%d_%H%M%S'), ext))
        shutil.copy2(path, dst + '.part')
        os.replace(dst + '.part', dst)
        for f in (olds + [os.path.basename(dst)])[:-keep]:
            os.remove(os.path.join(d, f))
        return dst
    except Exception as e:  # noqa: BLE001
        print('[WARN] image_curate 백업 실패 %s: %s: %s' % (path, type(e).__name__, e))
        return None


def utf8_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
