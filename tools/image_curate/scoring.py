"""점수 계산 — numpy(+sklearn) 만 쓴다. report.py 와 Flask(app/image_curate.py) 가 같이 쓴다.

  knn_sim    가장 비슷한 이웃 k장과의 평균 코사인 유사도(낮을수록 컬렉션에서 동떨어짐)
  combined   동떨어짐 순위(0=좋음 ~ 1=정리 후보) — 판정이 쌓이기 전 첫 후보용
  model      사용자 판정(labels)으로 학습한 '제거될 확률'. 판정이 적으면 None
  final      model 이 있으면 model 순위만, 없으면 combined

2026-11-03 변경(eval_features.py·시간순 검증, 판정 3,446건/제거 438건):
  - 범용 미적 점수(LAION aesthetic)를 순위에서 뺐다(화면 표시용으로만 남김). 사용자 기준은 '여성 인물의 얼굴·몸의
    라인(가슴·엉덩이·잘록한 허리·얇지 않은 허벅지)·의상·포즈'라 범용 점수와 맞지 않고, 판정과 오히려 반대였다
    (묶음 안 AUC 0.40 — 제거한 쪽이 범용 점수가 더 높았다).
  - final 을 (combined + model)/2 → model 만으로. 동떨어짐+미적의 기본 점수는 묶음 안 AUC 0.32(반대 방향)라 반반
    섞으면 0.53(거의 무작위), 모델만이면 0.70 · 상위 20장에 그 묶음 제거의 44%(섞으면 18%).

2026-11-03 취향 모델 입력 = 전체 + 인물 영역 + 얼굴 영역 CLIP(features.py, model_input). 판정 3,746건/제거 472건:
  - 시간순 AUC 0.689 → 0.714 (전체 기간 평균), 최근 12묶음 0.705 → 0.764. 판정이 늘수록 차이가 커졌다
    (이전 판정 25/50/75/100% 로 학습 시 0.628/0.657/0.695/0.705 vs 0.676/0.718/0.736/0.764).
  - 효과 없던 것: C 조절(0.1~10, 1 이 최적), 최근 판정 가중(0.691), 이웃 판정 kNN(0.61~0.65),
    몸 라인 직접 측정(body_shape.py, 0.678~0.688).
  - features.py 결과가 아직 없는 이미지는 전체 자리에 embed.py 임베딩, 인물·얼굴 자리는 0(검출 실패와 같은 취급).
"""
from typing import Dict, List, Optional

import numpy as np

KNN_K = 10
DUP_THR = 0.97
# 취향 모델을 켜는 최소 판정 수. 2026-11-02 첫 판정(후보 150장 중 유지 약 30장)이면 넘는다.
MODEL_MIN_REMOVE = 10
MODEL_MIN_KEEP = 5
# 직접 '유지'로 판정한 이미지는 판정 없는 refine 이미지보다 강한 유지 신호로 본다
KEEP_WEIGHT = 3.0


def normalize(emb: np.ndarray) -> np.ndarray:
    E = emb.astype(np.float32)
    E /= np.linalg.norm(E, axis=1, keepdims=True)
    return E


def pct_rank(x: np.ndarray) -> np.ndarray:
    """0~1 백분위 순위(작은 값 = 0)."""
    r = np.empty(len(x), dtype=np.float64)
    r[np.argsort(x, kind='stable')] = np.arange(len(x))
    return r / max(len(x) - 1, 1)


def base_scores(E: np.ndarray, aes: np.ndarray, k: int = KNN_K, dup_thr: float = DUP_THR,
                block: int = 1024) -> Dict[str, np.ndarray]:
    """E: 정규화된 임베딩. 유사도 행렬을 통째로 만들지 않고(5.7k² float32 = 130MB) 행 블록 단위로 계산한다
    — Flask 서버 안에서 요청마다 돌기 때문. pairs: 유사도 dup_thr 이상인 (i, j) 쌍(i < j, 근접중복용)."""
    n = len(E)
    k = min(k, max(n - 1, 1))
    knn_sim = np.empty(n, dtype=np.float32)
    nn_max = np.empty(n, dtype=np.float32)
    pi, pj = [], []
    for s in range(0, n, block):
        S = E[s:s + block] @ E.T
        rows = np.arange(S.shape[0])
        S[rows, rows + s] = -1.0
        knn_sim[s:s + block] = np.partition(S, -k, axis=1)[:, -k:].mean(axis=1)
        nn_max[s:s + block] = S.max(axis=1)
        ii, jj = np.where(S >= dup_thr)
        keep = jj > ii + s
        pi.append(ii[keep] + s)
        pj.append(jj[keep])
    outlier_r = 1.0 - pct_rank(knn_sim)
    aes_r = 1.0 - pct_rank(aes)
    pairs = np.stack([np.concatenate(pi), np.concatenate(pj)], axis=1) if pi else np.zeros((0, 2), int)
    return {'knn_sim': knn_sim, 'nn_max': nn_max, 'pairs': pairs,
            'outlier_r': outlier_r, 'aes_r': aes_r, 'combined': outlier_r}   # aes 는 순위에서 뺐다(모듈 설명 참고)


def _l2(x: np.ndarray) -> np.ndarray:
    x = x.astype(np.float32)
    n = np.linalg.norm(x, axis=1, keepdims=True)
    return np.where(n > 0, x / np.maximum(n, 1e-12), 0.0).astype(np.float32)


def model_input(E_fallback: np.ndarray, feat: Optional[Dict[str, np.ndarray]], names: List[str]) -> np.ndarray:
    """취향 모델 입력 (N, 2304) = [전체 | 인물 | 얼굴] CLIP (각각 L2 정규화). names 는 파일명(base_name).
    feat(features.py 캐시)에 없는 이미지는 [E_fallback | 0 | 0]. feat 가 None 이면 (N, 768) E_fallback 그대로."""
    if feat is None:
        return E_fallback
    fi = {}
    for i, n in enumerate(feat['names']):
        fi[str(n).rsplit('/', 1)[-1]] = i
    idx = np.array([fi.get(n, -1) for n in names], dtype=int)
    has = idx >= 0
    d = E_fallback.shape[1]
    X = np.zeros((len(names), 3 * d), dtype=np.float32)
    X[:, :d] = E_fallback
    if has.any():
        X[has] = feat_rows(feat, idx[has])
    return X


def feat_rows(feat: Dict[str, np.ndarray], idx: np.ndarray) -> np.ndarray:
    """features.py 캐시의 idx 행 → 취향 모델 입력 [전체 | 인물 | 얼굴] (각각 L2 정규화)."""
    return np.hstack([_l2(feat['emb'][idx]), _l2(feat['emb_person'][idx]), _l2(feat['emb_face'][idx])])


def knn_sim_to(Q: np.ndarray, R: np.ndarray, k: int = KNN_K, exclude_self: bool = False,
               block: int = 1024) -> np.ndarray:
    """Q 각 행과 R 에서 가장 비슷한 k개의 평균 코사인 유사도(둘 다 L2 정규화). exclude_self: Q 가 R 과 같은 배열."""
    out = np.empty(len(Q), dtype=np.float32)
    for s in range(0, len(Q), block):
        S = Q[s:s + block] @ R.T
        if exclude_self:
            r = np.arange(S.shape[0])
            S[r, r + s] = -1.0
        out[s:s + block] = np.partition(S, -k, axis=1)[:, -k:].mean(axis=1)
    return out


def train_model(E_pool: np.ndarray, y_remove: np.ndarray, keep_mask: np.ndarray):
    """E_pool: refine 현재 이미지 + 판정된 이미지(보관함 포함)의 임베딩.
    y_remove: 1 = 사용자가 제거로 판정. 0 = 그 외(직접 '유지' 판정 + 판정 없는 refine 이미지).
    판정 없는 refine 이미지는 '대체로 좋다'는 약한 신호(PU 학습) — 이미 사용자가 골라 넣은 폴더라서."""
    if int(y_remove.sum()) < MODEL_MIN_REMOVE or int(keep_mask.sum()) < MODEL_MIN_KEEP:
        return None
    from sklearn.linear_model import LogisticRegression
    w = np.where(keep_mask, KEEP_WEIGHT, 1.0)
    clf = LogisticRegression(C=1.0, class_weight='balanced', max_iter=2000)
    clf.fit(E_pool, y_remove, sample_weight=w)
    return clf


def final_scores(combined: np.ndarray, model_prob: Optional[np.ndarray]) -> np.ndarray:
    if model_prob is None:
        return combined
    return pct_rank(model_prob)    # 모델이 켜지면 모델 순위만(모듈 설명 참고)


def dup_groups(pairs: np.ndarray, n: int) -> List[List[int]]:
    """base_scores 의 pairs(유사도 기준 이상 쌍)를 같은 그룹으로 묶는다(union-find). 큰 그룹부터."""
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i, j in pairs:
        parent[find(i)] = find(j)
    groups = {}  # type: Dict[int, List[int]]
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return sorted([g for g in groups.values() if len(g) > 1], key=len, reverse=True)
