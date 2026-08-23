# -*- coding: utf-8 -*-
"""현행 전략(S1 진입 + B 청산)의 CAGR 추정 (2026-08-19 작성).

건당 기대수익(+0.186%)은 CAGR이 아니다. CAGR은 사이징·후보 수·복리가 모두 들어간다.
라이브 설정 그대로 하루 단위 현금흐름을 돌려 연평균 복리수익률을 낸다.

  진입 : S1 = signal_days=1, 등락률>=3%, 종가위치>=0.6  (현행 라이브)
  청산 : B  = 손절 -6%(1~4일차 장중 저가) 또는 5일차 개장가 전량  (현행 라이브)
  사이징: CASH_DEPLOY_RATIO=0.65, BUY_SLOTS=5, POS_CAP_DIVISOR=5,
          예산 분모 = min(남은후보, 남은슬롯)  (2026-08-18 수정본)
  비용 : 왕복 0.2% (cash_ratio_test.COST)

★ 후보 풀(pool)이 CAGR을 크게 흔든다. 라이브는 reserved 교집합이라 하루 3~10종목 수준인데
  (2026-08-14 실측 7종목) 백테스트는 fire 픽 전체(일 38종목)다. pool로 그 규모를 흉내낸다.
  pool을 종가위치 상위 N개로 자르는 건 '내가 좋은 종목을 체크해뒀다'를 가정하는 낙관 방향이다.

⚠️ 이 값을 실계좌 기대치로 읽으면 안 되는 이유
  1. 시가총액 700억 / 평균거래대금 40억 필터를 재현하지 못한다(pkl에 시총 없음) → 소형주 유입
  2. reserved 교집합을 재현하지 못한다 → pool은 근사이고 낙관 방향
  3. 생존편향 — 상장폐지 종목이 pkl에 없다
  4. 경로 노이즈가 크다. max_hold_sweep.py에서 전체집합과 부분집합의 순서가 뒤집힌 전례가 있다.
     그래서 단일 경로가 아니라 부트스트랩 분포로 낸다.

━━━ 결과 (2026-08-19, pkl 2,858종목 / 2023-03-27 ~ 2026-08-11 = 3.38년, 후보 31,421건) ━━━

  후보풀        단일경로   CAGR   보유%   MDD%   부트평균   CAGR    CAGR범위    음수
  상위 7(실측)  +314.6%  52.4%  84.4  -44.6  +177.8%  33.8%  12.8~63.2%   0%
  상위 10       +303.3%  51.2%  84.4  -44.7  +140.3%  28.5%   3.9~47.0%   0%
  제한없음      +303.3%  51.2%  84.4  -44.7  +181.7%  33.9%   8.6~62.8%   0%

  ★★ 이 CAGR은 **쓰면 안 된다.** 거의 전부가 '상한가 종목을 종가에 매수할 수 있다'는
     가정에서 나온다. 실제로는 상한가에 매도 잔량이 없어 15:18 시장가 매수가 체결되지 않는다.

  근거 — 당일 등락률 28% 이상(상한가권)의 기여를 분리하면:

    집단                    건수     비용후%   상한가권 비중
    전체 후보             31,421    +0.197      2.8%
    전체 - 상한가권        30,535    +0.070      0.0%
    일별 종가위치 상위5     4,083    +0.485     18.1%
    일별 상위5 - 상한가권   4,067    **-0.124**   0.0%

    포트폴리오는 매일 종가위치 상위 5개를 사는데, 종가위치>=0.99가 상위5의 64.8%다.
    종가 = 고가는 상한가의 전형적 형태라 **종가위치 랭킹이 상한가를 6.5배 농축한다**
    (전체 2.8% → 상위5 18.1%). 그 737건의 건당이 +3.760%로 전체를 끌어올린다.
    상한가를 빼면 상위5 건당이 -0.124%로 마이너스가 되고 CAGR도 음수가 된다
    (노출 84% / 연 62.5회전 가정 시 대략 -5 ~ -10%).

  상한가 제외 전체 후보의 연도별 비용후: 2023 -0.018 / 2024 -0.052 / 2025 +0.303 / 2026 +0.008
  → 2025년 하나만 뚜렷하게 플러스다.

  ※ 이 +0.070%는 TRADING_RULES §3에 이미 적혀 있던 '비용 후 +0.067% = 간신히 본전 위'와
    거의 일치한다. 즉 프로젝트의 종전 평가가 맞았고, 최근 올라간 수치가 상한가 인공물이었다.

  ⚠️ 이 인공물이 오염시키는 범위 (종가위치 상위 N개 선택을 쓰는 것들)
       cash_ratio_test.py / max_hold_sweep.py / track_compare.py의 포트폴리오·부트스트랩 수치,
       그리고 이 파일. 절대 수치를 실계좌 기대치로 읽지 말 것.
     오염되지 않은 것 (전체 후보를 그대로 쓰는 건당 비교)
       strategy_matrix.py / exit_chandelier_test.py / exit_open_vs_close.py /
       entry_threshold_test.py — 상한가가 양쪽에 2.8%씩 균등하게 들어가므로 규칙 간 순위는 유효하다.
       다만 절대 수치는 상한가 제외 시 +0.197 → +0.070으로 내려간다.

  ※ 다음에 할 일: 상한가(및 종가위치>=0.99) 종목을 후보에서 제외하고 전체 검증을 다시 돌려야
    한다. 라이브도 그런 종목은 사실상 체결되지 않으니 진입 후보에서 빼는 게 맞다.

사용법:
    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe auto_trading/backtest/cagr_estimate.py
    ... --limit 400
"""
import argparse
import os
import sys
from typing import Optional

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from auto_trading.backtest import strategy_matrix as SM                     # noqa: E402
from auto_trading.backtest.entry_threshold_test import CLOSE_POS_MIN, STOP  # noqa: E402
from auto_trading.backtest.cash_ratio_test import simulate, COST            # noqa: E402

RATIO = 0.65
SLOTS = 5
DIVISOR = 5


def build(limit: Optional[int] = None):
    store, mkt, market_ret5 = SM.load_store(limit)
    print('S1 진입 + B 청산 후보 생성...', flush=True)
    rows = []
    for n, (code, d) in enumerate(store.items(), 1):
        if n % 500 == 0:
            print(f'  ... {n}/{len(store)}', flush=True)
        cl, lo, op, cpos = d['cl'], d['lo'], d['op'], d['cpos']
        sig = d['base'] & (d['chg'] >= 3.0)
        if not sig.any():
            continue
        sd = SM.signal_days(sig)
        for i in np.flatnonzero(sig & (sd == 1) & (cpos >= CLOSE_POS_MIN)):
            entry = cl[i]
            if entry <= 0 or i + 5 >= len(cl):
                continue
            ret, hold = None, 5
            for k in range(1, 5):
                if lo[i + k] / entry - 1 <= STOP:
                    ret, hold = STOP * 100, k
                    break
            if ret is None:
                ret = (op[i + 5] / entry - 1) * 100
            rows.append({'D': d['idx'][i], 'entry': entry, 'close_pos': cpos[i],
                         'ret': ret, 'hold': hold})
    return pd.DataFrame(rows)


def cagr(total_pct, years):
    return ((1 + total_pct / 100.0) ** (1.0 / years) - 1) * 100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--capital', type=int, default=1_990_000)
    ap.add_argument('--iters', type=int, default=25)
    args = ap.parse_args()

    X = build(limit=args.limit)
    d0, d1 = X['D'].min(), X['D'].max()
    years = (d1 - d0).days / 365.25
    per_day = X.groupby('D').size()
    print(f'\n후보 {len(X):,}건 / {d0.date()} ~ {d1.date()} ({years:.2f}년) / '
          f'하루 평균 {per_day.mean():.1f}종목')
    print(f'건당 기대수익 {X["ret"].mean() - COST * 100:+.3f}% (왕복비용 {COST:.1%} 차감)\n')

    hdr = (f'{"후보풀":<18}{"단일경로":>10}{"CAGR":>9}{"보유%":>8}{"MDD%":>8}'
           f'{"부트평균":>10}{"CAGR":>9}{"CAGR범위":>18}{"음수":>7}')
    print('=' * len(hdr))
    print(f'현행 S1+B / ratio {RATIO} / 슬롯 {SLOTS} / divisor {DIVISOR} / {args.iters}회 부트스트랩')
    print('=' * len(hdr))
    print(hdr)
    print('-' * len(hdr))

    rng = np.random.default_rng(20260819)
    for pool, label in ((7, '상위 7 (실측)'), (10, '상위 10'), (None, '제한없음')):
        s = simulate(X, args.capital, SLOTS, DIVISOR, RATIO, False, pool)
        tot = []
        for _ in range(args.iters):
            sub = X.groupby('D', group_keys=False).apply(
                lambda g: g.sample(max(1, int(len(g) * 0.8)),
                                   random_state=int(rng.integers(1 << 31))))
            tot.append(simulate(sub, args.capital, SLOTS, DIVISOR, RATIO, False, pool)['total'])
        tot = np.array(tot)
        cg = np.array([cagr(t, years) for t in tot])
        print(f'{label:<18}{s["total"]:>9.1f}%{cagr(s["total"], years):>8.1f}%'
              f'{s["util"]:>8.1f}{s["mdd"]:>8.1f}'
              f'{tot.mean():>9.1f}%{cg.mean():>8.1f}%'
              f'{f"{cg.min():.1f} ~ {cg.max():.1f}%":>18}{(tot < 0).mean() * 100:>6.0f}%')
    print()
    print('단일경로 = 후보 전체를 그대로 쓴 1회 시뮬 / 부트 = 하루 후보 80% 표집 재시뮬')
    print('CAGR = (1+총수익)^(1/년) - 1.  MDD는 취득원가 기준이라 실제보다 과소평가된다.')


if __name__ == '__main__':
    main()
