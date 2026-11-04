"""유지 vs 제거 이미지의 차이 + 몸 라인 측정값(body_shape.py)이 취향 모델을 낫게 하는지 (2026-11-03, 검증 전용).

    venv_imgml/Scripts/python.exe tools/image_curate/eval_body.py
"""
import json
import os
import sys
from collections import OrderedDict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

from tools.image_curate.body_shape import BODY_PATH
from tools.image_curate.common import CACHE_PATH, LABELS_PATH, base_name, utf8_stdout
from tools.image_curate.features import FEAT_PATH

LABEL_KO = OrderedDict([
    ('whr', '허리/엉덩이 비율(낮을수록 잘록)'), ('waist_bust', '허리/가슴 비율(낮을수록 잘록)'),
    ('hip_minus_waist', '엉덩이-허리 폭 차(클수록 굴곡)'), ('bust_minus_waist', '가슴-허리 폭 차(클수록 굴곡)'),
    ('bust_n', '가슴 폭 / 몸통 길이'), ('waist_n', '허리 폭 / 몸통 길이'), ('hip_n', '엉덩이 폭 / 몸통 길이'),
    ('thigh_n', '허벅지 폭 / 몸통 길이'), ('thigh_hip', '허벅지 / 엉덩이'), ('shoulder_n', '어깨 폭 / 몸통(정면일수록 큼)'),
])


def main() -> None:
    utf8_stdout()
    labels = json.load(open(LABELS_PATH, encoding='utf-8'))
    bz = np.load(BODY_PATH)
    bcols = [str(c) for c in bz['body_cols']]
    bi = {base_name(str(n)): i for i, n in enumerate(bz['names'])}
    old = np.load(CACHE_PATH)
    oi = {base_name(str(n)): i for i, n in enumerate(old['names'])}
    lab = sorted([(n, v) for n, v in labels.items()
                  if v.get('src') in ('candidate', 'restore') and n in bi and n in oi], key=lambda kv: kv[1].get('ts', ''))
    y = np.array([v['label'] == 'remove' for _, v in lab], dtype=int)
    Bd = bz['body'][[bi[n] for n, _ in lab]].astype(np.float64)
    valid = Bd[:, bcols.index('valid')] > 0
    print('판정 %d건 (제거 %d) · 몸 라인 측정 성공 %.1f%% (유지 %.1f%% / 제거 %.1f%%)' % (
        len(y), y.sum(), 100 * valid.mean(), 100 * valid[y == 0].mean(), 100 * valid[y == 1].mean()))

    print('\n[유지 vs 제거 — 측정 성공한 이미지 중앙값, AUC: 0.5보다 크면 값이 클수록 제거]')
    print('  %-34s %8s %8s %7s' % ('측정값', '유지', '제거', 'AUC'))
    yv = y[valid]
    for k, ko in LABEL_KO.items():
        x = Bd[valid, bcols.index(k)]
        ok = np.isfinite(x)
        print('  %-34s %8.3f %8.3f %7.3f' % (ko, np.median(x[ok & (yv == 0)]), np.median(x[ok & (yv == 1)]),
                                           roc_auc_score(yv[ok], x[ok])))

    # 정면에 가까운(어깨가 넓게 보이는) 서 있는/앉은 사진만 — 폭 측정이 가장 믿을 만한 경우
    sh = Bd[:, bcols.index('shoulder_n')]
    front = valid & np.isfinite(sh) & (sh >= 0.6)
    yf = y[front]
    print('\n[정면에 가까운 사진만 (%d장, 제거 %d)]' % (front.sum(), yf.sum()))
    for k in ('whr', 'waist_bust', 'hip_minus_waist', 'bust_n', 'hip_n', 'thigh_n'):
        x = Bd[front, bcols.index(k)]
        ok = np.isfinite(x)
        print('  %-34s %8.3f %8.3f %7.3f' % (LABEL_KO[k], np.median(x[ok & (yf == 0)]), np.median(x[ok & (yf == 1)]),
                                           roc_auc_score(yf[ok], x[ok])))

    # 모델에 넣었을 때(시간순)
    E = old['emb'][[oi[n] for n, _ in lab]].astype(np.float64)
    E /= np.linalg.norm(E, axis=1, keepdims=True)
    feat = Bd.copy()
    feat[~np.isfinite(feat)] = np.nan
    ts = np.array([v.get('ts', '') for _, v in lab])
    batches = OrderedDict()
    for i, (_, v) in enumerate(lab):
        if v.get('src') == 'candidate':
            batches.setdefault(v.get('ts', ''), []).append(i)

    def run(use_emb, use_body, w=0.3):
        aucs, caps = [], []
        for t, te in batches.items():
            te = np.array(te)
            tr = np.where(ts < t)[0]
            yt = y[te]
            if len(tr) < 200 or y[tr].sum() < 10 or yt.sum() in (0, len(yt)):
                continue
            Xa, Xb = [], []
            if use_emb:
                Xa.append(E[tr]); Xb.append(E[te])
            if use_body:
                med = np.nanmedian(feat[tr], axis=0)
                fa = np.where(np.isnan(feat[tr]), med, feat[tr]); fb = np.where(np.isnan(feat[te]), med, feat[te])
                sc = StandardScaler().fit(fa)
                Xa.append(sc.transform(fa) * w); Xb.append(sc.transform(fb) * w)
            m = LogisticRegression(C=1.0, class_weight='balanced', max_iter=4000).fit(np.hstack(Xa), y[tr])
            p = m.predict_proba(np.hstack(Xb))[:, 1]
            aucs.append(roc_auc_score(yt, p))
            caps.append(yt[np.argsort(-p)[:20]].sum() / yt.sum())
        return np.mean(aucs), np.mean(caps)

    print('\n[취향 모델 — 시간순 검증]')
    for name, e, b, w in (('지금(CLIP)', True, False, 0), ('몸 라인 측정만', False, True, 1.0),
                          ('CLIP + 몸 라인(약하게 0.3)', True, True, 0.3), ('CLIP + 몸 라인(1.0)', True, True, 1.0)):
        a, c = run(e, b, w)
        print('  %-28s 시간순 AUC %.3f  상위20 포착 %.0f%%' % (name, a, 100 * c))


if __name__ == '__main__':
    main()
