"""취향 모델 입력 비교 — 어떤 특징이 사용자의 제거/유지 판정을 더 잘 맞히나 (2026-11-02, 검증 전용).

    venv_imgml/Scripts/python.exe tools/image_curate/eval_features.py

판정: labels.json 의 후보 탭 판정(src=candidate) + 복원(src=restore, 유지). 중복 탭 판정은 '둘 중 덜 나은 쪽'이라 뺀다
(정리 화면의 취향 모델과 같은 기준).

지표
  CV AUC      5겹 교차검증. 0.5 = 무작위, 1.0 = 완벽
  시간순 AUC  각 확정 묶음(100장)을 '그 이전 판정만'으로 학습한 모델로 매겨 본다 = 실제 사용 상황. 묶음별 평균
  상위20 포착  그 묶음의 제거 중 모델 상위 20장 안에 든 비율(무작위면 20%). 화면 앞쪽에 몰리는 정도
"""
import json
import os
import sys
from collections import OrderedDict
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler

from tools.image_curate.common import CACHE_PATH, LABELS_PATH, base_name, utf8_stdout
from tools.image_curate.features import FEAT_PATH


def _l2(x: np.ndarray) -> np.ndarray:
    x = x.astype(np.float64)
    n = np.linalg.norm(x, axis=1, keepdims=True)
    return np.where(n > 0, x / np.maximum(n, 1e-12), 0.0)


def build(blocks: Dict[str, np.ndarray], use: List[str], tr: np.ndarray, te: np.ndarray):
    """블록을 이어 붙인다. 임베딩은 L2 정규화 그대로, 스칼라(scal·aes)는 학습셋 기준 표준화."""
    a, b = [], []
    for k in use:
        x = blocks[k]
        if k in ('scal', 'aes', 'aes_old'):
            s = StandardScaler().fit(x[tr])
            a.append(s.transform(x[tr])); b.append(s.transform(x[te]))
        else:
            a.append(x[tr]); b.append(x[te])
    return np.hstack(a), np.hstack(b)


def fit_pred(blocks, use, y, tr, te, C=1.0):
    Xa, Xb = build(blocks, use, tr, te)
    m = LogisticRegression(C=C, max_iter=4000, class_weight='balanced')
    m.fit(Xa, y[tr])
    return m.predict_proba(Xb)[:, 1]


def main() -> None:
    utf8_stdout()
    labels = json.load(open(LABELS_PATH, encoding='utf-8'))
    with np.load(FEAT_PATH, allow_pickle=False) as z:
        f = {k: z[k] for k in z.files}
    with np.load(CACHE_PATH, allow_pickle=False) as z:
        old = {k: z[k] for k in z.files}
    fi = {base_name(str(n)): i for i, n in enumerate(f['names'])}
    oi = {base_name(str(n)): i for i, n in enumerate(old['names'])}

    lab = [(n, v) for n, v in labels.items()
           if v.get('src') in ('candidate', 'restore') and n in fi and n in oi]
    lab.sort(key=lambda kv: kv[1].get('ts', ''))
    y = np.array([v['label'] == 'remove' for _, v in lab], dtype=int)
    ix = np.array([fi[n] for n, _ in lab]); ox = np.array([oi[n] for n, _ in lab])
    cols = [str(c) for c in f['scal_cols']]
    blocks = {
        'old': _l2(old['emb'][ox]),                    # 지금 정리 화면이 쓰는 것
        'aes_old': old['aes'][ox].astype(np.float64)[:, None],
        'full': _l2(f['emb'][ix]),                     # quickgelu 로 바로잡은 전체 이미지
        'aes': f['aes'][ix].astype(np.float64)[:, None],
        'person': _l2(f['emb_person'][ix]),
        'face': _l2(f['emb_face'][ix]),
        'scal': f['scal'][ix].astype(np.float64),
    }
    S = blocks['scal']
    print('판정 %d건 (제거 %d) · 인물 검출 %.1f%% · 얼굴 %.1f%%' % (
        len(y), y.sum(), 100 * S[:, cols.index('has_person')].mean(), 100 * S[:, cols.index('has_face')].mean()))

    # 단일 특징이 제거와 어떤 관계인가(방향 확인용)
    print('\n[단일 지표 AUC — 0.5 보다 크면 값이 클수록 제거, 작으면 값이 작을수록 제거]')
    for k in ('face_sharp', 'face_size', 'person_sharp', 'person_area', 'n_persons', 'cut_top', 'cut_bottom', 'n_kp_vis'):
        x = S[:, cols.index(k)]
        print('  %-13s %.3f' % (k, roc_auc_score(y, x)))
    print('  %-13s %.3f' % ('aes(바로잡음)', roc_auc_score(y, blocks['aes'][:, 0])))
    print('  %-13s %.3f' % ('aes(지금)', roc_auc_score(y, blocks['aes_old'][:, 0])))

    configs = OrderedDict([
        ('지금(전체 CLIP, 기존 캐시)', ['old']),
        ('전체 CLIP(quickgelu)', ['full']),
        ('인물 영역 CLIP', ['person']),
        ('얼굴 영역 CLIP', ['face']),
        ('스칼라(선명도·구도·포즈 좌표)', ['scal']),
        ('전체 + 인물', ['full', 'person']),
        ('전체 + 인물 + 얼굴', ['full', 'person', 'face']),
        ('전체 + 인물 + 얼굴 + 스칼라', ['full', 'person', 'face', 'scal']),
        ('전부 + aes', ['full', 'person', 'face', 'scal', 'aes']),
    ])

    batches = OrderedDict()
    for i, (_, v) in enumerate(lab):
        if v.get('src') == 'candidate':
            batches.setdefault(v.get('ts', ''), []).append(i)
    ts_all = np.array([v.get('ts', '') for _, v in lab])
    cv = StratifiedKFold(5, shuffle=True, random_state=0)

    print('\n%-30s %7s %9s %10s' % ('입력', 'CV AUC', '시간순 AUC', '상위20 포착'))
    for name, use in configs.items():
        p = np.zeros(len(y))
        for tr, te in cv.split(np.zeros(len(y)), y):
            p[te] = fit_pred(blocks, use, y, tr, te)
        cv_auc = roc_auc_score(y, p)
        aucs, caps = [], []
        for t, te in batches.items():
            te = np.array(te)
            tr = np.where(ts_all < t)[0]
            yt = y[te]
            if len(tr) < 200 or y[tr].sum() < 10 or yt.sum() == 0 or yt.sum() == len(yt):
                continue
            pt = fit_pred(blocks, use, y, tr, te)
            aucs.append(roc_auc_score(yt, pt))
            top = np.argsort(-pt)[:20]
            caps.append(yt[top].sum() / yt.sum())
        print('%-30s %7.3f %9.3f %9.0f%%   (묶음 %d개)' % (name, cv_auc, np.mean(aucs), 100 * np.mean(caps), len(aucs)))


if __name__ == '__main__':
    main()
