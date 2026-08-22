# -*- coding: utf-8 -*-
"""상한가 제외 후 전체 재검증 (2026-08-19 작성).

계기: cagr_estimate.py에서 '종가위치 상위 N개' 선택이 상한가 종목을 6.5배 농축하고
      (전체 2.8% → 상위5 18.1%), 그 737건(건당 +3.760%)이 포트폴리오 수치를 전부 만들고
      있었다는 것을 발견했다. 상한가는 매도 잔량이 없어 15:18 시장가로 살 수 없다.

이 스크립트가 답해야 하는 것:
  A. CLOSE_POS_MIN=0.6의 근거가 상한가 인공물인가?
     (first_signal_filter.py의 '종가위치 0.85~1.0 → +1.175%'가 상한가 때문이었는지)
  B. 청산 규칙 순위(현행 B > 트레일링)가 상한가 제외 후에도 유지되는가?
  C. 상한가를 후보에서 뺀 현실적인 CAGR은 얼마인가?

━━━ 상한가 정의 (두 수준을 같이 낸다) ━━━
  E1 좁게 : 등락률 >= 28% AND 종가위치 >= 0.99  — 상한가에 잠겨 종가=고가인 명백한 케이스
  E2 넓게 : 등락률 >= 28%                        — 상한가권 전체
  국내 일일 제한폭이 +-30%이므로 28% 이상은 사실상 상한가 근처다.

진입은 S1(signal_days=1, 등락률>=3%)을 쓰고 **종가위치 필터는 걸지 않은 상태로** 만든 뒤
분석 단계에서 스윕한다 — 그래야 필터 자체를 검증할 수 있다.

━━━ 결과 (2026-08-19, pkl 2,858종목 / 2023-03~2026-08, 후보 42,877건, 비용후 %) ━━━
  상한가권(등락률>=28%) 889건(2.1%) — 그중 867건이 종가위치>=0.99. E1과 E2가 거의 같다.

  A. 종가위치 구간별 (청산 B)      상한가 포함    상한가 제외(E2)
     0.00~0.30                  -0.563        -0.558
     0.30~0.60                  -0.457        -0.462
     0.60~0.85                  +0.075        +0.075
     0.85~0.99                  +0.058        +0.060
     0.99~1.01                  **+1.120**    **+0.079**   ← 붕괴

  ★ first_signal_filter.py의 '종가위치 0.85~1.0 → +1.175%'는 **상한가 때문이었다.**
    상한가를 빼면 0.60 이상 세 구간이 +0.06~0.08로 평평하다.

  B. CLOSE_POS_MIN 스윕            상한가 포함    상한가 제외(E2)
     0.00                        +0.016        -0.080
     0.30                        +0.049        -0.053
     0.60                        +0.197        **+0.070**  ← 최적
     0.85                        +0.328        +0.062

  ★ **필터 자체는 살아남는다** — 0.6 미만은 음수, 0.6 이상은 양수. 0.6이 최적값이다.
    다만 kiwoom_fire_strategy.py BUY_SLOTS 주석의 '상위로 좁힐수록 단조 증가
    (상위20 +0.664 → 5 +1.166 → 3 +1.879)'는 상한가 인공물이다. 0.85는 0.60보다 낫지 않다.
    → BUY_SLOTS=5의 근거 중 '상위 집중' 항목은 무효. '자본 활용도' 항목만 남는다.

  C. 청산 규칙 순위                상한가 포함    상한가 제외(E2)
     B 손절-6%+5일                +0.197        +0.070
     A 트레일링15일                -0.846        -1.066
  ★ 순위 유지되고 격차가 오히려 벌어진다(0.69 → 1.14%p). 트레일링·샹들리에 기각,
    5일 보유 유지 등 **청산 관련 결론은 모두 그대로 유효하다.**

  D. CAGR (종가위치>=0.6 / ratio 0.65 / 슬롯5 / 후보풀 상위7 / 25회 부트, 3.38년)
     상한가 포함    부트 CAGR **+33.8%**  (12.8~63.2%)  음수 0%   MDD -44.6
     E1 제외        부트 CAGR **-8.3%**   (-25.9~8.6%)  음수 88%  MDD -59.7
     E2 제외        부트 CAGR **-9.9%**   (-29.1~2.8%)  음수 84%  MDD -59.3

  E. 상한가 제외 후 ratio 스윕 — **어떤 노출로도 플러스가 안 된다**
     ratio  보유%   CAGR    음수   MDD%
     0.15   32.2   -4.8%   96%   -28.9   ← 최선(=거래를 줄이는 것)
     0.25   48.4   -7.7%   96%   -42.4
     0.35   60.4   -8.4%   96%   -47.8
     0.50   73.0  -10.9%  100%   -60.0
     0.65   82.5   -9.0%   92%   -59.3   ← 현행
     0.80   89.1  -10.6%   84%   -66.6
     건당 +0.070%로는 변동성 끌림을 못 이긴다. 사이징으로 해결되는 문제가 아니다.

⚠️ 이 결론을 뒤집을 수 있는 **유일한 미확인 요소는 시가총액 700억 / 평균거래대금 40억 필터**다
   (pkl에 시총이 없어 재현 불가 → 소형주가 대량 유입된 상태). interest_stocks DB에는 신호별
   market_value가 있으므로 DB 기간(2025-09~)에 한해 그 필터의 효과를 따로 측정할 수 있다.
   reserved 교집합(내 종목 선택)도 미재현이며, TRADING_RULES §8-1은 종목 선택이 사이징보다
   성과에 훨씬 큰 영향을 준다고 적고 있다(27.0% vs 37.2%). 생존편향은 반대 방향(실제가 더 나쁨).

사용법:
    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe auto_trading/backtest/limitup_recheck.py
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

from auto_trading.backtest import fire_backtest_regen as R                 # noqa: E402
from auto_trading.backtest import strategy_matrix as SM                    # noqa: E402
from auto_trading.backtest.entry_threshold_test import STOP                # noqa: E402
from auto_trading.backtest.cash_ratio_test import simulate                 # noqa: E402

COST = 0.2          # % 왕복비용
LIMIT_CHG = 28.0    # 상한가권 등락률 기준
RATIO, SLOTS, DIVISOR = 0.65, 5, 5


def build(limit: Optional[int] = None):
    store, mkt, market_ret5 = SM.load_store(limit)
    print('후보 생성 (종가위치 필터 없음) + 청산 2규칙...', flush=True)
    rows = []
    for n, (code, d) in enumerate(store.items(), 1):
        if n % 500 == 0:
            print(f'  ... {n}/{len(store)}', flush=True)
        cl, lo, op, cpos, chg = d['cl'], d['lo'], d['op'], d['cpos'], d['chg']
        sig = d['base'] & (chg >= 3.0)
        if not sig.any():
            continue
        sd = SM.signal_days(sig)
        for i in np.flatnonzero(sig & (sd == 1)):
            entry = cl[i]
            if entry <= 0 or i + 5 >= len(cl):
                continue
            # 청산 B: 손절 -6%(1~4일차) 아니면 5일차 개장가
            b, hold = None, 5
            for k in range(1, 5):
                if lo[i + k] / entry - 1 <= STOP:
                    b, hold = STOP * 100, k
                    break
            if b is None:
                b = (op[i + 5] / entry - 1) * 100
            # 청산 A: 트레일링 15일
            res = R.simulate_exit(d['df'][SM.OHLC], i, entry, 15)
            a = np.nan
            if res is not None and res.get('exit') != 'truncated' \
                    and 'truncated' not in str(res.get('exit_seq', '')):
                a = res['ret_pct']
            rows.append({'D': d['idx'][i], 'entry': entry, 'close_pos': cpos[i],
                         'chg': chg[i], 'ret': b, 'hold': hold, 'a': a})
    return pd.DataFrame(rows)


def masks(X):
    e1 = ~((X['chg'] >= LIMIT_CHG) & (X['close_pos'] >= 0.99))
    e2 = X['chg'] < LIMIT_CHG
    return [('상한가 포함(원본)', pd.Series(True, index=X.index)),
            ('E1 상한가잠김 제외', e1),
            ('E2 상한가권 제외', e2)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--capital', type=int, default=1_990_000)
    ap.add_argument('--iters', type=int, default=25)
    args = ap.parse_args()

    X = build(limit=args.limit)
    X = X[X['ret'].notna()]
    years = (X['D'].max() - X['D'].min()).days / 365.25
    print(f'\n후보 {len(X):,}건 (종가위치 필터 없음) / {X["D"].min().date()} ~ '
          f'{X["D"].max().date()} ({years:.2f}년)')
    print(f'상한가권(등락률>={LIMIT_CHG:.0f}%) {(X["chg"] >= LIMIT_CHG).sum():,}건 '
          f'({(X["chg"] >= LIMIT_CHG).mean():.1%}) / '
          f'그중 종가위치>=0.99 {((X["chg"] >= LIMIT_CHG) & (X["close_pos"] >= 0.99)).sum():,}건\n')

    # ── A. 종가위치 구간별 — 상한가가 만든 효과였는지 ──────────────────────
    print('=' * 96)
    print('A. 종가위치 구간별 건당 수익률 (청산 B, 왕복비용 0.2% 차감)')
    print('=' * 96)
    buckets = [(0.0, 0.3), (0.3, 0.6), (0.6, 0.85), (0.85, 0.99), (0.99, 1.01)]
    print(f'{"종가위치":<14}' + ''.join(f'{lab:>22}' for lab, _ in masks(X)))
    print('-' * 96)
    for lo, hi in buckets:
        line = f'{f"{lo:.2f}~{hi:.2f}":<14}'
        for lab, m in masks(X):
            s = X[m & (X['close_pos'] >= lo) & (X['close_pos'] < hi)]
            line += (f'{s["ret"].mean() - COST:>13.3f} ({len(s):>5,})' if len(s) > 200
                     else f'{"(표본부족)":>22}')
        print(line)
    print()

    # ── B. CLOSE_POS_MIN 스윕 ─────────────────────────────────────────────
    print('=' * 96)
    print('B. CLOSE_POS_MIN 스윕 — 필터가 상한가 없이도 유효한가 (청산 B)')
    print('=' * 96)
    print(f'{"CLOSE_POS_MIN":<14}' + ''.join(f'{lab:>22}' for lab, _ in masks(X)))
    print('-' * 96)
    for th in (0.0, 0.3, 0.6, 0.85):
        line = f'{th:<14.2f}'
        for lab, m in masks(X):
            s = X[m & (X['close_pos'] >= th)]
            line += f'{s["ret"].mean() - COST:>13.3f} ({len(s):>5,})'
        print(line)
    print()

    # ── C. 청산 규칙 순위 ──────────────────────────────────────────────────
    print('=' * 96)
    print('C. 청산 규칙 순위 (종가위치>=0.6 적용)')
    print('=' * 96)
    print(f'{"청산":<20}' + ''.join(f'{lab:>22}' for lab, _ in masks(X)))
    print('-' * 96)
    for col, name in (('ret', 'B 손절-6%+5일'), ('a', 'A 트레일링15일')):
        line = f'{name:<20}'
        for lab, m in masks(X):
            s = X[m & (X['close_pos'] >= 0.6) & X[col].notna()]
            line += f'{s[col].mean() - COST:>13.3f} ({len(s):>5,})'
        print(line)
    print()

    # ── D. CAGR 재계산 ────────────────────────────────────────────────────
    print('=' * 96)
    print(f'D. CAGR 재계산 (종가위치>=0.6 / ratio {RATIO} / 슬롯 {SLOTS} / 후보풀 상위7 / '
          f'{args.iters}회 부트)')
    print('=' * 96)
    print(f'{"상한가 처리":<22}{"단일 총수익":>13}{"CAGR":>9}{"부트평균":>11}{"CAGR":>9}'
          f'{"CAGR범위":>19}{"음수":>7}{"MDD%":>8}')
    print('-' * 96)
    rng = np.random.default_rng(20260819)

    def boot(C, ratio):
        s = simulate(C, args.capital, SLOTS, DIVISOR, ratio, False, 7)
        tot = []
        for _ in range(args.iters):
            sub = C.groupby('D', group_keys=False).apply(
                lambda g: g.sample(max(1, int(len(g) * 0.8)),
                                   random_state=int(rng.integers(1 << 31))))
            tot.append(simulate(sub, args.capital, SLOTS, DIVISOR, ratio, False, 7))
        tot_pct = np.array([t['total'] for t in tot])
        cg = np.array([((1 + t / 100) ** (1 / years) - 1) * 100 if t > -100 else -99.9
                       for t in tot_pct])
        return s, tot_pct, cg, float(np.mean([t['util'] for t in tot]))

    for lab, m in masks(X):
        C = X[m & (X['close_pos'] >= 0.6)][['D', 'entry', 'close_pos', 'ret', 'hold']].copy()
        s, tot, cg, _ = boot(C, RATIO)
        one = ((1 + s['total'] / 100) ** (1 / years) - 1) * 100
        print(f'{lab:<22}{s["total"]:>12.1f}%{one:>8.1f}%{tot.mean():>10.1f}%'
              f'{cg.mean():>8.1f}%{f"{cg.min():.1f} ~ {cg.max():.1f}%":>19}'
              f'{(tot < 0).mean() * 100:>6.0f}%{s["mdd"]:>8.1f}')
    print()

    # ── E. 상한가 제외 상태에서 노출(ratio)을 다시 훑는다 ──────────────────
    # 건당 기대값이 +0.07% 수준으로 내려갔으므로, 어제 정한 ratio 0.65(보유 79%)가
    # 과대노출일 수 있다. 변동성 끌림 때문에 산술평균이 양수여도 기하평균은 음수가 된다.
    print('=' * 96)
    print(f'E. 상한가권 제외(E2) 상태의 ratio 스윕 — 종가위치>=0.6 / 후보풀 상위7 / '
          f'{args.iters}회 부트')
    print('=' * 96)
    print(f'{"ratio":>7}{"보유%":>8}{"현금%":>8}{"부트 총수익":>13}{"CAGR":>9}'
          f'{"CAGR범위":>19}{"음수":>7}{"MDD%":>8}')
    print('-' * 96)
    C = X[(X['chg'] < LIMIT_CHG) & (X['close_pos'] >= 0.6)][
        ['D', 'entry', 'close_pos', 'ret', 'hold']].copy()
    for ratio in (0.15, 0.25, 0.35, 0.50, 0.65, 0.80):
        s, tot, cg, util = boot(C, ratio)
        print(f'{ratio:>7.2f}{util:>8.1f}{100 - util:>8.1f}{tot.mean():>12.1f}%'
              f'{cg.mean():>8.1f}%{f"{cg.min():.1f} ~ {cg.max():.1f}%":>19}'
              f'{(tot < 0).mean() * 100:>6.0f}%{s["mdd"]:>8.1f}')
    print()


if __name__ == '__main__':
    main()
