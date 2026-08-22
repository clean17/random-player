# -*- coding: utf-8 -*-
"""슬롯 수 결정 — 고정 vs 동적(현금 비례) 포트폴리오 시뮬레이션 (2026-08-14 작성).

새 전략 전체를 하루 단위 현금흐름으로 시뮬레이션한다.
  진입: 첫 신호일(signal_days=1) + 종가위치 >= 0.6, 종가위치 높은순으로 슬롯만큼 매수
  청산: 손절 -6%(장중 저가 터치) 또는 5거래일 보유 만기
  사이징: 가용현금 * CASH_DEPLOY_RATIO / 슬롯수 (종목당 상한 = 같은 값)

비교 대상
  고정 슬롯 3 / 5 / 10 / 20
  동적 슬롯 = 가용현금 / UNIT  (UNIT = 30만 / 50만 / 100만)

측정: 총수익, 연환산 Sharpe, MDD, 1주도 못 산 비율(nocash), 평균 보유종목수
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

from auto_trading.backtest.first_signal_filter import build  # noqa: E402
from auto_trading.backtest.fire_backtest_regen import load_ohlc  # noqa: E402

CLOSE_POS_MIN = 0.6
STOP = -0.06
MAX_HOLD = 5
DEPLOY_RATIO = 0.70
COST = 0.002        # 왕복 거래비용


def precompute_exits(X):
    """각 후보의 청산 결과(보유일수, 수익률)를 미리 계산."""
    out = []
    for code, g in X.groupby('code'):
        o = load_ohlc(code)
        if o is None:
            continue
        for _, r in g.iterrows():
            i = o.index.searchsorted(r['D'])
            if i >= len(o) or o.index[i] != r['D']:
                continue
            entry = float(o['종가'].iloc[i])
            if entry <= 0:
                continue
            ret, hold = None, MAX_HOLD
            for k in range(1, MAX_HOLD + 1):
                j = i + k
                if j >= len(o):
                    hold = k - 1
                    break
                if float(o['저가'].iloc[j]) / entry - 1 <= STOP:
                    ret, hold = STOP * 100, k
                    break
            if ret is None:
                j = min(i + hold, len(o) - 1)
                if j <= i:
                    continue
                ret = (float(o['종가'].iloc[j]) / entry - 1) * 100
            out.append({'D': r['D'], 'code': code, 'entry': entry,
                        'close_pos': r['close_pos'], 'ret': ret, 'hold': hold})
    return pd.DataFrame(out)


def simulate(cand, capital, slots=None, unit=None):
    """slots 고정 또는 unit(현금/unit)로 동적 결정."""
    days = sorted(cand['D'].unique())
    by_day = {d: g.sort_values('close_pos', ascending=False) for d, g in cand.groupby('D')}
    cash = float(capital)
    cost_basis = 0.0
    open_pos = []          # {'exit_i', 'proceeds', 'cost'}
    equity, npos, nocash, attempts = [], [], 0, 0

    for i, d in enumerate(days):
        still = []
        for p in open_pos:
            if p['exit_i'] <= i:
                cash += p['proceeds']
                cost_basis -= p['cost']
            else:
                still.append(p)
        open_pos = still

        n_slot = slots if slots else max(1, int(cash // unit))
        limit = max(0.0, cash) * DEPLOY_RATIO
        per = limit / n_slot if n_slot > 0 else 0
        bought = 0
        for _, r in by_day.get(d, pd.DataFrame()).iterrows():
            if bought >= n_slot:
                break
            attempts += 1
            budget = min(per, cash)
            qty = int(budget // r['entry'])
            if qty <= 0:
                nocash += 1
                continue
            spent = qty * r['entry']
            proceeds = spent * (1 + r['ret'] / 100.0) * (1 - COST)
            cash -= spent
            cost_basis += spent
            open_pos.append({'exit_i': min(i + int(r['hold']), len(days) - 1),
                             'proceeds': proceeds, 'cost': spent})
            bought += 1
        equity.append(cash + cost_basis)
        npos.append(len(open_pos))

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
        'nocash': (nocash / attempts * 100) if attempts else 0.0,
        'avg_pos': float(np.mean(npos)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--capital', type=int, default=2_290_000, help='실계좌 현재 총자산')
    args = ap.parse_args()

    X = build()
    X = X[X['close_pos'] >= CLOSE_POS_MIN].copy()
    print(f'후보 {len(X):,}건 (첫 신호일 + 종가위치>={CLOSE_POS_MIN})')
    cand = precompute_exits(X)
    print(f'청산 계산 완료 {len(cand):,}건 / 평균 보유 {cand["hold"].mean():.2f}일 / '
          f'건당 {cand["ret"].mean():+.3f}%\n')

    for capital in (args.capital, 5_000_000, 10_000_000):
        print('=' * 88)
        print(f'초기자본 {capital:,}원 (왕복비용 {COST:.1%} 반영)')
        print('=' * 88)
        print(f'{"슬롯 방식":<26}{"총수익%":>10}{"Sharpe":>9}{"MDD%":>9}'
              f'{"nocash%":>9}{"평균보유":>9}')
        print('-' * 88)
        for n in (3, 5, 10, 20):
            r = simulate(cand, capital, slots=n)
            print(f'{f"고정 {n}슬롯":<26}{r["total"]:>10.1f}{r["sharpe"]:>9.2f}'
                  f'{r["mdd"]:>9.1f}{r["nocash"]:>9.1f}{r["avg_pos"]:>9.1f}')
        print('-' * 88)
        for unit in (300_000, 500_000, 1_000_000):
            r = simulate(cand, capital, unit=unit)
            print(f'{f"동적 현금/{unit // 10000}만원":<26}{r["total"]:>10.1f}{r["sharpe"]:>9.2f}'
                  f'{r["mdd"]:>9.1f}{r["nocash"]:>9.1f}{r["avg_pos"]:>9.1f}')
        print()


if __name__ == '__main__':
    main()
