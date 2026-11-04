"""몸의 라인 측정 — 인물 윤곽(마스크)에서 가슴·허리·엉덩이·허벅지 폭을 잰다 (2026-11-03, 실험 단계).

    venv_imgml/Scripts/python.exe tools/image_curate/body_shape.py     # features.py 를 먼저 돌려 둘 것(관절 좌표 사용)

사용자 기준(2026-11-03): 가슴·엉덩이가 크고 허리가 잘록하면서 허벅지가 얇지 않은 몸. CLIP 은 '잘록한 허리'를
'마른 몸'과 같은 뜻으로 받아들여(설명 상관 +0.39, 제거 쪽) '볼륨은 크고 허리만 가는' 조합을 못 가른다 → 직접 잰다.

방법
  1) torchvision 공식 Mask R-CNN(COCO) 으로 사람 마스크. features.py 의 주 인물 상자와 가장 많이 겹치는 마스크를 고른다.
  2) 어깨 중점 S → 골반 중점 H 를 몸통 축으로 잡고(기울어진 자세도 축을 따라 잰다), 축을 따라 일정 간격으로
     수직선 위 마스크 폭(축 위 점을 포함하는 연속 구간)을 잰다. 몸통 길이 Lt = |H - S| 로 나눠 크기와 무관하게.
       가슴 = 0.15~0.45 Lt 구간 최대, 허리 = 0.45~0.9 최소, 엉덩이 = 0.85~1.35 최대,
       허벅지 = 골반~무릎의 40% 지점(무릎이 안 보이면 1.5 Lt) 마스크 합(두 다리)
  3) 비율: 허리/엉덩이(WHR), 허리/가슴, 각 폭/몸통 길이, 허벅지/엉덩이, 어깨폭/몸통(정면·측면 구분용), 폭 프로필 19점

한계: 팔이 몸통에 붙어 있으면 폭에 같이 잡힌다. 옆모습은 폭이 아니라 앞뒤 두께(가슴·엉덩이 돌출)를 잰 값이 된다.
캐시: cache/refine_body.npz
"""
import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
import torch
import torchvision
from PIL import Image, ImageFile

from tools.image_curate.common import CACHE_DIR, base_name, resolve_ref_dir, utf8_stdout
from tools.image_curate.features import FEAT_PATH, KP_NAMES

ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = None

BODY_PATH = os.path.join(CACHE_DIR, 'refine_body.npz')
SIDE = 1024
PROFILE_T = np.linspace(-0.1, 1.7, 19)
BODY_COLS = (['valid', 'whr', 'waist_bust', 'bust_n', 'waist_n', 'hip_n', 'thigh_n', 'thigh_hip', 'shoulder_n',
              'hip_minus_waist', 'bust_minus_waist', 'torso_tilt']
             + ['prof_%02d' % i for i in range(len(PROFILE_T))])


def _load(path: str) -> Optional[Image.Image]:
    try:
        with Image.open(path) as im:
            im.seek(0)
            im = im.convert('RGB')
            s = SIDE / max(im.size)
            if s < 1:
                im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.BILINEAR)
            return im
    except Exception as e:  # noqa: BLE001
        print('  [skip] %s: %s' % (os.path.basename(path), e))
        return None


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def _run_width(mask: np.ndarray, c: np.ndarray, v: np.ndarray, R: float, contiguous: bool) -> float:
    """c 를 지나 v 방향 선 위의 마스크 폭(픽셀). contiguous: c 를 포함하는 연속 구간만(팔 분리), 아니면 합(두 다리)."""
    h, w = mask.shape
    s = np.arange(-int(R), int(R) + 1, dtype=np.float32)
    px = np.round(c[0] + s * v[0]).astype(int)
    py = np.round(c[1] + s * v[1]).astype(int)
    ok = (px >= 0) & (px < w) & (py >= 0) & (py < h)
    inside = np.zeros(len(s), bool)
    inside[ok] = mask[py[ok], px[ok]]
    if not contiguous:
        return float(inside.sum())
    mid = len(s) // 2
    if not inside[mid]:
        near = np.where(inside)[0]
        if not len(near):
            return np.nan
        j = near[np.argmin(np.abs(near - mid))]
        if abs(j - mid) > 0.1 * R:
            return np.nan
        mid = j
    lo = mid
    while lo > 0 and inside[lo - 1]:
        lo -= 1
    hi = mid
    while hi < len(s) - 1 and inside[hi + 1]:
        hi += 1
    return float(hi - lo + 1)


def measure(mask: np.ndarray, kp: np.ndarray, vis: np.ndarray) -> np.ndarray:
    """mask: (h,w) bool, kp: (17,2) 픽셀 좌표, vis: (17,) bool → BODY_COLS 벡터(못 재면 valid=0, 나머지 nan)."""
    out = np.full(len(BODY_COLS), np.nan, np.float32)
    out[0] = 0
    ix = {n: i for i, n in enumerate(KP_NAMES)}
    sh = [kp[ix[k]] for k in ('lsho', 'rsho') if vis[ix[k]]]
    hp = [kp[ix[k]] for k in ('lhip', 'rhip') if vis[ix[k]]]
    if not sh or not hp:
        return out
    S, H = np.mean(sh, 0), np.mean(hp, 0)
    Lt = float(np.linalg.norm(H - S))
    if Lt < 20:
        return out
    u = (H - S) / Lt
    v = np.array([-u[1], u[0]])
    R = 1.2 * Lt
    # 관절이 마스크와 어긋나면(다른 사람·특이한 자세) 몸통 축이 마스크 밖으로 나간다 — 그런 측정은 버린다
    hh, ww = mask.shape
    ax = [S + t * (H - S) for t in np.linspace(0, 1, 11)]
    inside = [0 <= int(p[0]) < ww and 0 <= int(p[1]) < hh and mask[int(p[1]), int(p[0])] for p in ax]
    if np.mean(inside) < 0.8:
        return out
    prof = np.array([_run_width(mask, S + t * Lt * u, v, R, True) for t in PROFILE_T]) / Lt

    def rng(a, b, fn):
        sel = prof[(PROFILE_T >= a) & (PROFILE_T <= b)]
        sel = sel[~np.isnan(sel)]
        return float(fn(sel)) if len(sel) else np.nan

    bust, waist, hip = rng(0.15, 0.45, np.max), rng(0.45, 0.9, np.min), rng(0.85, 1.35, np.max)
    if not (np.isfinite(bust) and np.isfinite(waist) and np.isfinite(hip)) or not (0.35 <= waist / hip <= 1.3):
        return out   # 사람 몸에서 나올 수 없는 비율 = 측정 실패
    kn = [kp[ix[k]] for k in ('lknee', 'rknee') if vis[ix[k]]]
    tc = H + 0.4 * (np.mean(kn, 0) - H) if kn else S + 1.5 * Lt * u
    thigh = _run_width(mask, tc, v, R, False) / Lt
    shoulder = float(np.linalg.norm(sh[0] - sh[1])) / Lt if len(sh) == 2 else np.nan
    vals = {'valid': 1.0, 'whr': waist / hip, 'waist_bust': waist / bust, 'bust_n': bust, 'waist_n': waist,
            'hip_n': hip, 'thigh_n': thigh, 'thigh_hip': thigh / hip, 'shoulder_n': shoulder,
            'hip_minus_waist': hip - waist, 'bust_minus_waist': bust - waist,
            'torso_tilt': float(np.degrees(np.arctan2(u[0], u[1])))}
    for i, c in enumerate(BODY_COLS):
        if c in vals:
            out[i] = vals[c]
    out[BODY_COLS.index('prof_00'):] = prof
    return out


def main() -> None:
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default=None)
    ap.add_argument('--batch', type=int, default=8)
    ap.add_argument('--limit', type=int, default=0)
    args = ap.parse_args()
    ref_dir = resolve_ref_dir(args.dir)
    with np.load(FEAT_PATH, allow_pickle=False) as z:
        f = {k: z[k] for k in z.files}
    cols = [str(c) for c in f['scal_cols']]
    ci = {c: i for i, c in enumerate(cols)}
    names = [str(n) for n in f['names']]
    if args.limit:
        names = names[:args.limit]
    print('대상', len(names), '(features.py 결과 기준)')

    dev = 'cuda' if torch.cuda.is_available() else 'cpu'
    W = torchvision.models.detection.MaskRCNN_ResNet50_FPN_V2_Weights.COCO_V1
    m = torchvision.models.detection.maskrcnn_resnet50_fpn_v2(weights=W, box_score_thresh=0.5,
                                                              min_size=640, max_size=SIDE).to(dev).eval()
    tt = torchvision.transforms.functional.to_tensor
    pool = ThreadPoolExecutor(max_workers=8)
    rows = np.full((len(names), len(BODY_COLS)), np.nan, np.float32)
    rows[:, 0] = 0
    t0 = time.time()
    for b in range(0, len(names), args.batch):
        chunk = list(range(b, min(b + args.batch, len(names))))
        ims = list(pool.map(lambda i: _load(os.path.join(ref_dir, names[i])), chunk))
        ok = [(i, im) for i, im in zip(chunk, ims) if im is not None and f['scal'][i, ci['has_person']] > 0]
        if ok:
            with torch.no_grad(), torch.autocast(dev, dtype=torch.float16, enabled=(dev == 'cuda')):
                outs = m([tt(im).to(dev) for _, im in ok])
            for (i, im), o in zip(ok, outs):
                s = f['scal'][i]
                Wd, Hd = im.size
                ph, pa = s[ci['person_h']], s[ci['person_area']]
                bw = pa / max(ph, 1e-6)
                x0, y0 = s[ci['person_cx']] - bw / 2, s[ci['person_cy']] - ph / 2
                kbox = np.array([x0 * Wd, y0 * Hd, (x0 + bw) * Wd, (y0 + ph) * Hd])
                lab = o['labels'].cpu().numpy()
                boxes = o['boxes'].float().cpu().numpy()
                cand = [j for j in range(len(lab)) if lab[j] == 1]
                if not cand:
                    continue
                j = max(cand, key=lambda q: _iou(boxes[q], kbox))
                if _iou(boxes[j], kbox) < 0.3:
                    continue
                mask = (o['masks'][j, 0] > 0.5).cpu().numpy()
                kp = np.zeros((17, 2), np.float32)
                vis = np.zeros(17, bool)
                for k, n in enumerate(KP_NAMES):
                    if s[ci['kp_%s_v' % n]] > 0:
                        vis[k] = True
                        kp[k] = ((x0 + s[ci['kp_%s_x' % n]] * bw) * Wd, (y0 + s[ci['kp_%s_y' % n]] * ph) * Hd)
                rows[i] = measure(mask, kp, vis)
        done = chunk[-1] + 1
        if (b // args.batch) % 20 == 0 or done == len(names):
            el = time.time() - t0
            print('  %d/%d  %.0fs  (%.1f장/s)' % (done, len(names), el, done / max(el, 1e-6)), flush=True)
    pool.shutdown()
    np.savez(BODY_PATH, names=np.array(names, dtype=str), body=rows, body_cols=np.array(BODY_COLS, dtype=str))
    print('저장:', BODY_PATH, '· 측정 성공 %.1f%%' % (100 * np.nanmean(rows[:, 0])))


if __name__ == '__main__':
    main()
