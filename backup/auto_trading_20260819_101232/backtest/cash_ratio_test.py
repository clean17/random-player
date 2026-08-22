# -*- coding: utf-8 -*-
"""CASH_DEPLOY_RATIO 결정 + 예산 분모 버그 수정 검증 (2026-08-18 작성).

계기: 2026-08-14 실매매에서 가용현금 1,989,709원 중 325,840원(16.4%)만 집행됐다.
원인은 두 가지였다.
  (1) POS_CAP_DIVISOR=20인데 후보가 7종목뿐이라 종목당 상한이 69,640원으로 쪼개짐
      (8/15 커밋 90a6bcc에서 divisor 20→5로 이미 수정됨)
  (2) 예산 분모가 '남은 후보 수'라, 후보가 슬롯보다 많은 날엔 한도를 후보 수로 나눠 놓고
      슬롯이 먼저 소진돼 한도의 (후보-슬롯)/후보가 통째로 남음

이 스크립트는 (2)의 수정 효과와, 사용자가 요청한 '현금 20%' 목표에 맞는 deploy_ratio를
같은 조건에서 비교한다.

진입/청산은 slot_sizing_test.py(BUY_SLOTS=5 결정 근거)와 동일하게 맞춘다:
  진입: 첫 신호일(signal_days=1) + 종가위치 >= 0.6, 종가위치 높은순
  청산: 손절 -6%(장중 저가 터치) 또는 5거래일 보유 만기
  왕복비용 0.2%

사이징 규칙 두 가지를 비교한다:
  old : budget = (limit - deployed) / max(1, 남은후보)          ← 8/18 이전 (버그)
  new : budget = (limit - deployed) / max(1, min(남은후보, 남은슬롯))  ← 수정본
  둘 다 spendable = min(budget, pos_cap, limit - deployed), pos_cap = limit / divisor

★ 후보 풀 크기가 결정적이다. 백테스트는 fire 픽 전체를 후보로 쓰지만 라이브는 reserved
  교집합이라 훨씬 작다(2026-08-14 실측 7종목). --pool N으로 하루 후보를 상위 N개로 잘라
  reserved 규모를 흉내낸다. 무작위가 아니라 종가위치 상위 N개를 남기는데, 이건 '내가 좋은
  종목을 체크해뒀다'를 가정하는 낙관 방향이므로 결과를 그렇게 읽어야 한다.

사용법:
    venv/Scripts/python.exe auto_trading/backtest/cash_ratio_test.py
    venv/Scripts/python.exe auto_trading/backtest/cash_ratio_test.py --pool 7 --capital 1990000
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

from auto_trading.backtest.first_signal_filter import build            # noqa: E402
from auto_trading.backtest.slot_sizing_test import precompute_exits    # noqa: E402
from auto_trading.backtest.slot_sizing_test import CLOSE_POS_MIN       # noqa: E402

COST = 0.002        # 왕복 거래비용 (실계좌 추정치, TRADING_RULES §8-4)
RATIOS = (0.70, 0.80, 0.90, 1.00)   # --ratios로 덮어쓴다


def simulate(cand, capital, slots, divisor, ratio, fixed_denom, pool=None):
    """하루 단위 현금흐름 시뮬레이션.

    fixed_denom=True  → old 규칙(분모 = 남은 후보 수)
    fixed_denom=False → new 규칙(분모 = min(남은 후보, 남은 슬롯))
    """
    days = sorted(cand['D'].unique())
    by_day = {d: g.sort_values('close_pos', ascending=False) for d, g in cand.groupby('D')}

    cash = float(capital)
    cost_basis = 0.0
    open_pos = []
    equity, util, limit_use, nocash, attempts = [], [], [], 0, 0

    for i, d in enumerate(days):
        still = []
        for p in open_pos:
            if p['exit_i'] <= i:
                cash += p['proceeds']
                cost_basis -= p['cost']
            else:
                still.append(p)
        open_pos = still

        rows = by_day.get(d)
        rows = [] if rows is None else list(rows.itertuples(index=False))
        if pool:
            rows = rows[:pool]          # reserved 교집합 규모 흉내 (종가위치 상위 N개)

        limit = max(0.0, cash) * ratio
        pos_cap = (limit / divisor) if divisor else float('inf')
        deployed = 0.0
        bought = 0

        for k, r in enumerate(rows):
            if bought >= slots:
                break
            attempts += 1
            denom = (len(rows) - k) if fixed_denom else min(len(rows) - k, slots - bought)
            budget = (limit - deployed) / max(1, denom)
            budget = min(budget, pos_cap, limit - deployed, cash)
            qty = int(budget // r.entry)
            if qty <= 0:
                nocash += 1
                continue
            spent = qty * r.entry
            cash -= spent
            cost_basis += spent
            deployed += spent
            bought += 1
            open_pos.append({'exit_i': min(i + int(r.hold), len(days) - 1),
                             'proceeds': spent * (1 + r.ret / 100.0) * (1 - COST),
                             'cost': spent})

        equity.append(cash + cost_basis)
        total = cash + cost_basis
        util.append(cost_basis / total if total > 0 else 0.0)
        if rows and limit > 0:
            limit_use.append(deployed / limit)

    for p in open_pos:
        cash += p['proceeds']
        cost_basis -= p['cost']
    final = cash + cost_basis

    eq = np.array(equity + [final], dtype=float)
    peak = np.maximum.accumulate(eq)
    rets = np.diff(eq) / eq[:-1]
    rets = rets[np.isfinite(rets)]
    sharpe = (rets.mean() / rets.std() * np.sqrt(252)) if len(rets) > 1 and rets.std() > 0 else 0.0

    return {
        'total': (final / capital - 1) * 100,
        'sharpe': sharpe,
        'mdd': float(((eq - peak) / peak).min()) * 100,
        'util': float(np.mean(util)) * 100,
        'cash': 100 - float(np.mean(util)) * 100,
        'limit_use': float(np.mean(limit_use)) * 100 if limit_use else 0.0,
        'nocash': (nocash / attempts * 100) if attempts else 0.0,
    }


HDR = (f'{"규칙":<6}{"ratio":>7}{"이론보유%":>10}{"실측보유%":>10}{"현금%":>8}'
       f'{"한도소진%":>10}{"총수익%":>9}{"Sharpe":>8}{"MDD%":>8}{"nocash%":>9}')


def table(cand, capital, slots, divisor, pool, h, title):
    print('=' * 96)
    print(title)
    print('=' * 96)
    print(HDR)
    print('-' * 96)
    for ratio in RATIOS:
        for label, fixed in (('old', True), ('new', False)):
            s = simulate(cand, capital, slots, divisor, ratio, fixed, pool)
            u_theory = h * ratio / (1 + h * ratio) * 100
            print(f'{label:<6}{ratio:>7.2f}{u_theory:>10.1f}{s["util"]:>10.1f}{s["cash"]:>8.1f}'
                  f'{s["limit_use"]:>10.1f}{s["total"]:>9.1f}{s["sharpe"]:>8.2f}'
                  f'{s["mdd"]:>8.1f}{s["nocash"]:>9.1f}')
        print('-' * 96)
    print()


def bootstrap(cand, capital, slots, divisor, pool, n_iter, frac=0.8, seed=20260818):
    """후보를 하루 단위로 frac만큼 표집해 n_iter번 재시뮬레이션.

    단일 경로는 노이즈가 지배한다 — slot_sizing_test.py에서도 부트스트랩 평균 +18.0%인 설정의
    단일 경로가 사실상 본전(229만→227만)이었다. ratio 같은 노출 파라미터는 경로 분산이 더
    크므로 분포로 판단해야 한다.
    """
    rng = np.random.default_rng(seed)
    ratios = RATIOS
    acc = {(lbl, r): [] for lbl in ('old', 'new') for r in ratios}

    for _ in range(n_iter):
        sub = cand.groupby('D', group_keys=False).apply(
            lambda g: g.sample(max(1, int(len(g) * frac)), random_state=int(rng.integers(1 << 31))))
        for r in ratios:
            for lbl, fixed in (('old', True), ('new', False)):
                acc[(lbl, r)].append(simulate(sub, capital, slots, divisor, r, fixed, pool))

    print('=' * 96)
    print(f'부트스트랩 {n_iter}회 (하루 후보 {frac:.0%} 표집) — '
          f'초기자본 {capital:,}원 / 슬롯 {slots} / divisor {divisor} / '
          f'{f"후보 상위 {pool}개" if pool else "후보 제한 없음"}')
    print('=' * 96)
    print(f'{"규칙":<6}{"ratio":>7}{"보유%":>8}{"현금%":>8}'
          f'{"총수익 평균":>12}{"표준편차":>10}{"최저":>9}{"최고":>9}{"음수비율":>10}{"MDD평균":>10}')
    print('-' * 96)
    for r in ratios:
        for lbl in ('old', 'new'):
            v = acc[(lbl, r)]
            tot = np.array([x['total'] for x in v])
            print(f'{lbl:<6}{r:>7.2f}'
                  f'{np.mean([x["util"] for x in v]):>8.1f}'
                  f'{np.mean([x["cash"] for x in v]):>8.1f}'
                  f'{tot.mean():>12.1f}{tot.std():>10.1f}{tot.min():>9.1f}{tot.max():>9.1f}'
                  f'{(tot < 0).mean() * 100:>10.0f}'
                  f'{np.mean([x["mdd"] for x in v]):>10.1f}')
        print('-' * 96)
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--capital', type=int, default=1_990_000, help='초기자본 (기본 2026-08-14 실계좌)')
    ap.add_argument('--slots', type=int, default=5, help='BUY_SLOTS')
    ap.add_argument('--divisor', type=int, default=5, help='POS_CAP_DIVISOR')
    ap.add_argument('--pool', type=int, default=None, help='하루 후보 상한 (reserved 규모 흉내)')
    ap.add_argument('--bootstrap', type=int, default=0, help='부트스트랩 반복 횟수 (0이면 단일 경로만)')
    ap.add_argument('--ratios', type=str, default=None, help='쉼표구분 deploy_ratio 목록 (예 0.55,0.65,0.75)')
    args = ap.parse_args()

    if args.ratios:
        global RATIOS
        RATIOS = tuple(float(x) for x in args.ratios.split(','))

    X = build()
    X = X[X['close_pos'] >= CLOSE_POS_MIN].copy()
    print(f'후보 {len(X):,}건 (첫 신호일 + 종가위치>={CLOSE_POS_MIN})')
    cand = precompute_exits(X)
    h = cand['hold'].mean()
    per_day = cand.groupby('D').size()
    print(f'청산 계산 완료 {len(cand):,}건 / {cand["D"].nunique()}거래일 / '
          f'평균 보유 {h:.2f}일 / 건당 {cand["ret"].mean():+.3f}%')
    print(f'하루 후보 수: 평균 {per_day.mean():.1f} 중앙값 {per_day.median():.0f} '
          f'(라이브 reserved 교집합은 2026-08-14 기준 7종목)\n')
    print('이론보유% = h·r/(1+h·r) — 정상상태 보유비율. 한도소진% = 그날 집행액/그날 매수한도.\n')

    pools = [args.pool] if args.pool else [None, 10, 7]
    for pool in pools:
        tag = f'후보 상위 {pool}개로 제한 (reserved 흉내)' if pool else '후보 제한 없음 (fire 픽 전체)'
        table(cand, args.capital, args.slots, args.divisor, pool, h,
              f'초기자본 {args.capital:,}원 / 슬롯 {args.slots} / divisor {args.divisor} / {tag}')

    if args.bootstrap:
        for pool in pools:
            bootstrap(cand, args.capital, args.slots, args.divisor, pool, args.bootstrap)


if __name__ == '__main__':
    main()
