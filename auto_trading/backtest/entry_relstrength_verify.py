# -*- coding: utf-8 -*-
"""interest_v2(상대강도 밴드) 전환이 실제 mock 사이징에서 CAGR을 양수로 바꾸는지 검증
(2026-08-24 작성).

계기: 매도 규칙 쪽 탐색(exit_scalp_creative_search.py)에서 fire 진입신호 자체가 시험구간
전 구간에서 기대값 음수임을 확인했다("매도로는 못 고친다"). 레짐게이트/H2는 이미 기각된
방법이라 배제하고, track_compare.py가 이미 찾아둔 '상대강도 밴드'(interest_v2) 대안을
fire의 실제 mock 사이징(슬롯20/divisor20/2,400만원/후보 20개/ratio 0.75)으로 재검증한다.

track_compare.py의 기존 결과(재사용, 여기서 다시 구하지 않음):
  - 신호 품질: interest 건당 -0.013% vs v2 +0.174% (3년 전체)
  - walk-forward(2025-01-01 이전 데이터로만 밴드 보정 후 2025+ 시험): interest +0.163%
    vs v2(재보정밴드) +0.457% — 시험구간을 전혀 안 보고 뽑은 밴드로도 우위 유지.
  - 포트폴리오(슬롯5/divisor5/후보7): interest -18.8% vs v2 +14.0% (절대값은 신뢰 말 것 —
    시총 필터 미재현 + 2024 포함 혼합구간).

여기서 새로 하는 것: track_compare.build()의 두 트랙을 그대로 가져와
  1) 시험구간만(D >= SPLIT) 떼어 out-of-sample 결과만 헤드라인으로 보고
  2) cash_ratio_test.simulate()/bootstrap()으로 fire의 실제 mock 사이징(슬롯20/
     divisor20/2,400만원/후보 20개/ratio 0.75)에서 포트폴리오 CAGR을 부트스트랩 30회로 낸다.

사용법:
    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe auto_trading/backtest/entry_relstrength_verify.py
    ... --limit 500   (빠른 확인)
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

from auto_trading.backtest.track_compare import build, COST     # noqa: E402
from auto_trading.backtest.cash_ratio_test import simulate      # noqa: E402

SPLIT = pd.Timestamp('2025-01-01')     # track_compare.py의 walk-forward 분할과 동일
CAPITAL = 24_000_000                   # mock 계좌 근사치 (2026-08-24 실측)
SLOTS = 20
DIVISOR = 20
POOL = 20                              # reserved 교집합 근사 (실측 18~22)
RATIO = 0.75                           # 2026-08-24 변경된 mock CASH_DEPLOY_RATIO


def cagr(total_pct, years):
    return ((1 + total_pct / 100) ** (1 / years) - 1) * 100 if total_pct > -100 else -99.9


def portfolio_bootstrap(C, n_iter, seed):
    years = (C['D'].max() - C['D'].min()).days / 365.25
    rng = np.random.default_rng(seed)
    tots, utils = [], []
    for _ in range(n_iter):
        sub = C.groupby('D', group_keys=False).apply(
            lambda g: g.sample(max(1, int(len(g) * 0.8)), random_state=int(rng.integers(1 << 31))))
        o = simulate(sub, CAPITAL, SLOTS, DIVISOR, RATIO, False, POOL)
        tots.append(o['total'])
        utils.append(o['util'])
    tots = np.array(tots)
    cg = np.array([cagr(t, years) for t in tots])
    return {
        'years': years, 'util': float(np.mean(utils)),
        'cagr_mean': cg.mean(), 'cagr_lo': cg.min(), 'cagr_hi': cg.max(),
        'neg_pct': float((tots < 0).mean() * 100),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--iters', type=int, default=30)
    args = ap.parse_args()

    tracks, *_ = build(limit=args.limit)

    print(f'=== 시험구간(out-of-sample, D >= {SPLIT.date()}) 신호 품질 ===')
    for name, X in tracks.items():
        te = X[X['D'] >= SPLIT]
        if len(te) < 30:
            print(f'{name:<10} 표본부족 ({len(te)}건)')
            continue
        net = te['ret'].mean() - COST * 100
        print(f'{name:<10} 건수 {len(te):>6,}  건당(비용후) {net:+.3f}%  '
              f'승률 {(te["ret"] > COST*100).mean()*100:.1f}%  '
              f'신호일 {te["D"].nunique()}일  신호일당 {len(te)/max(1,te["D"].nunique()):.1f}종목')

    print(f'\n=== 포트폴리오 부트스트랩 {args.iters}회 (mock 실사이징: 슬롯{SLOTS}/divisor{DIVISOR}/'
          f'{CAPITAL:,}원/후보상위{POOL}/ratio{RATIO}, 시험구간만) ===')
    print(f'{"트랙":<10}{"연수":>6}{"보유%":>7}{"CAGR평균":>10}{"CAGR범위":>18}{"음수경로%":>10}')
    print('-' * 70)
    for name, X in tracks.items():
        te = X[X['D'] >= SPLIT][['D', 'entry', 'close_pos', 'ret', 'hold']].copy()
        if len(te) < 100:
            print(f'{name:<10}   (표본부족 {len(te)}건)')
            continue
        r = portfolio_bootstrap(te, args.iters, seed=20260824)
        rng_txt = f'{r["cagr_lo"]:.1f} ~ {r["cagr_hi"]:.1f}%'
        print(f'{name:<10}{r["years"]:>6.2f}{r["util"]:>7.1f}{r["cagr_mean"]:>9.1f}%'
              f'{rng_txt:>18}{r["neg_pct"]:>9.0f}%')


if __name__ == '__main__':
    main()
