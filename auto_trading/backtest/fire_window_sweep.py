# -*- coding: utf-8 -*-
"""FIRE_WINDOW_DAYS(현재 6) 대신 다른 창 길이가 더 나은 CAGR을 내는지 스윕 (2026-08-26 작성).

계기: 사용자가 fire 쿼리의 집계 기간(FIRE_WINDOW_DAYS)을 바꾸면 더 좋은 CAGR이 나오는지 물음.
직전 두 조사의 결론을 그대로 전제한다 — (1) 매도 전략으로는 못 고친다(진입 신호 자체가 마이너스
기대값), (2) target='interest' → 'interest_v2'(상대강도 밴드)로 바꾸면 아웃오브샘플에서
CAGR이 양수로 돌아선다(재보정 밴드 기준 +6.5%, 부트스트랩 30회 전부 플러스). 이번 스윕은 그
interest_v2 위에 창 길이만 바꿔본다 — interest(구 트랙)는 다시 보지 않는다.

━━━ FIRE_WINDOW_DAYS가 실제로 하는 일 ━━────────────────────────────────────────
get_fire_candidates()가 `date~endDate = 오늘-N일~오늘`로 interest_stocks를 모아
총상승률(그 구간 내 최저가 대비 최근가)을 계산한다. 이 코드베이스의 기존 pkl 재현
(entry_timing.py, entry_threshold_test.py, track_compare.py)은 이 창을 CLUSTER_GAP으로
근사한다 — "직전 신호일과 CLUSTER_GAP영업일 이상 떨어져야 새 신호 묶음(=새 진입 기회)"라는
규칙인데, SQL의 "오늘-N일~오늘 창 안에 신호 이력이 있으면 계속 같은 묶음"과 동치에 가깝다.
이 스크립트는 그 기존 근사를 그대로 쓰고 CLUSTER_GAP만 파라미터화한다 — 새 하네스를
만들지 않는다(track_compare.py의 exits()를 cluster_gap 인자로만 복제).

⚠️ 근사의 한계: 실제 SQL은 "오늘 기준으로 매일 다시" 최저가를 계산하는 이동창인데,
클러스터링은 "묶음 시작일 종가 대비"로 고정한다. 방향은 같지만 정확히 같은 계산은 아니다
(track_compare.py도 같은 근사를 쓰고 있어 상대 비교에는 문제없다).

사용법:
    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe auto_trading/backtest/fire_window_sweep.py
    ... --windows 3,4,5,6,7,8,10,12,15
    ... --bootstrap 30
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from auto_trading.backtest.entry_threshold_test import (                 # noqa: E402
    MAX_HOLD, STOP, COST, CLOSE_POS_MIN,
)
from auto_trading.backtest.track_compare import (                        # noqa: E402
    load_market_map, prep, make_track as _make_track_fixed_gap,
    REL_STRENGTH_LO, REL_STRENGTH_HI, V2_MIN_RATE, net,
)
from auto_trading.kiwoom_fire_strategy_mock import PKL_DIR                    # noqa: E402
import auto_trading.backtest.cash_ratio_test as crt                      # noqa: E402

crt.RATIOS = (0.75,)   # mock의 실제 CASH_DEPLOY_RATIO 하나만 본다(기본 4개 스윕 대신)
bootstrap = crt.bootstrap

SPLIT = pd.Timestamp('2025-01-01')   # track_compare.py / 직전 조사와 동일한 train/test 경계


def exits_with_gap(d: pd.DataFrame, hits: np.ndarray, cluster_gap: int):
    """track_compare.exits()를 cluster_gap 파라미터화한 것 (그 외 로직은 동일)."""
    if len(hits) == 0:
        return []
    firsts = [hits[0]]
    for a, b in zip(hits[:-1], hits[1:]):
        if b - a > cluster_gap:
            firsts.append(b)

    close = d['close'].to_numpy()
    low = d['low'].to_numpy()
    cpos = d['close_pos'].to_numpy()
    chg = d['chg'].to_numpy()
    idx = d.index

    recs = []
    for i in firsts:
        if i + 1 >= len(close) or close[i] <= 0 or cpos[i] < CLOSE_POS_MIN:
            continue
        entry = close[i]
        ret, hold = None, MAX_HOLD
        for k in range(1, MAX_HOLD + 1):
            j = i + k
            if j >= len(close):
                hold = k - 1
                break
            if low[j] / entry - 1 <= STOP:
                ret, hold = STOP * 100, k
                break
        if ret is None:
            j = min(i + hold, len(close) - 1)
            if j <= i:
                continue
            ret = (close[j] / entry - 1) * 100
        recs.append({'D': idx[i], 'entry': entry, 'close_pos': cpos[i],
                     'chg': chg[i], 'ret': ret, 'hold': hold})
    return recs


def make_track_v2(store, mkt, market_ret5, cluster_gap: int):
    """interest_v2(상대강도 밴드) 신호를 주어진 cluster_gap으로 생성."""
    recs = []
    for code, d in store.items():
        base = d['base'].to_numpy()
        chg = d['chg'].to_numpy()
        m = mkt.get(code)
        if m not in market_ret5:
            continue
        rel = (d['ret5'] - market_ret5[m].reindex(d.index)).to_numpy()
        cond = base & (chg >= V2_MIN_RATE) & (rel >= REL_STRENGTH_LO) & (rel <= REL_STRENGTH_HI)
        for r in exits_with_gap(d, np.flatnonzero(cond), cluster_gap):
            r['code'] = code
            recs.append(r)
    return pd.DataFrame(recs)


def build_store(limit=None):
    mkt = load_market_map()
    files = [f for f in os.listdir(PKL_DIR) if f.endswith('.pkl')]
    if limit:
        files = files[:limit]
    print(f'1차 패스: {len(files)}종목 지표 계산 + 시장 평균 5일수익률 집계...', flush=True)
    store = {}
    ret5_by_market = {'kospi': {}, 'kosdaq': {}}
    for n, fname in enumerate(files, 1):
        if n % 500 == 0:
            print(f'  ... {n}/{len(files)}', flush=True)
        code = fname[:-4]
        d = prep(os.path.join(PKL_DIR, fname))
        if d is None:
            continue
        store[code] = d
        m = mkt.get(code)
        if m in ret5_by_market:
            ret5_by_market[m][code] = d['ret5']
    market_ret5 = {}
    for m, series in ret5_by_market.items():
        if series:
            market_ret5[m] = pd.DataFrame(series).mean(axis=1)
            print(f'  {m}: {len(series)}종목')
    return store, mkt, market_ret5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--windows', type=str, default='3,4,5,6,7,8,10,12,15')
    ap.add_argument('--bootstrap', type=int, default=30)
    ap.add_argument('--capital', type=int, default=24_000_000)
    args = ap.parse_args()
    windows = [int(x) for x in args.windows.split(',')]

    store, mkt, market_ret5 = build_store(limit=args.limit)

    print('\n' + '=' * 118)
    print('A. 신호 품질 — 건당, IS(<2025)/OOS(>=2025) (interest_v2, 상대강도 밴드 2.8~7.1 고정)')
    print('=' * 118)
    hdr = (f'{"창(일)":>7}{"건수":>9}{"일평균":>8}  |{"훈련 건수":>10}{"훈련 비용후%":>12}{"훈련 승률":>9}'
           f'  |{"시험 건수":>10}{"시험 비용후%":>12}{"시험 승률":>9}')
    print(hdr)
    print('-' * 118)

    tracks = {}
    for w in windows:
        X = make_track_v2(store, mkt, market_ret5, w)
        tracks[w] = X
        if X.empty:
            print(f'{w:>7}   (신호 없음)')
            continue
        days = X['D'].nunique()
        tr = X[X['D'] < SPLIT]
        te = X[X['D'] >= SPLIT]
        def seg(s):
            if len(s) < 100:
                return f'{len(s):>10,}{"(표본부족)":>12}{"":>9}'
            return f'{len(s):>10,}{net(s["ret"]):>12.3f}{(s["ret"] > 0).mean() * 100:>8.1f}%'
        print(f'{w:>7}{len(X):>9,}{len(X) / max(1, days):>8.1f}  |{seg(tr)}  |{seg(te)}')
    print()

    print('=' * 118)
    print(f'B. 포트폴리오 OOS(>= {SPLIT.date()}) 부트스트랩 {args.bootstrap}회 '
          f'(슬롯20/divisor20/{args.capital:,}원/후보상위20/ratio 0.75/왕복비용 0.2%)')
    print('=' * 118)
    for w in windows:
        X = tracks.get(w)
        if X is None or X.empty:
            continue
        oos = X[X['D'] >= SPLIT].reset_index(drop=True)
        if len(oos) < 300:
            print(f'창 {w}일: OOS 표본 부족({len(oos)}건) — 포트폴리오 시뮬 생략')
            continue
        print(f'\n---- 창 {w}일 (OOS 신호 {len(oos):,}건) ----')
        bootstrap(oos, args.capital, slots=20, divisor=20, pool=20, n_iter=args.bootstrap)


if __name__ == '__main__':
    main()
