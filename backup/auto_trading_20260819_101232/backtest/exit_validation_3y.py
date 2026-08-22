# -*- coding: utf-8 -*-
"""청산 규칙 개선안 3년 검증 (2026-08-14 작성).

배경: 1년치(fire_backtest_result_current.csv)에서 '현재 청산 규칙이 -0.78%p를 깎는다'는 결과가
나왔지만, 레짐 게이트 검증에서 '전체 평균은 좋아 보여도 2026년 한 해가 만든 착시'인 사례를
겪었다. 그래서 청산 개선안도 반영 전에 3년치·연도별 일관성을 확인한다.

판정 기준: 개선안이 진짜라면 **모든 해에서** 현행보다 높아야 한다.

신호는 advanced_threshold_sweep.build_signals()로 3년치를 재구성한다(2_finding_stocks_advanced
재현). 청산은 두 갈래로 잰다.
  - rule  : fire_backtest_regen.simulate_exit (트레일링/손절/정체보호 — 실제 코드와 같은 로직)
  - plain : 단순 규칙 (N일 보유 / 손절 / 익절) — 직접 구현
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

from auto_trading.backtest import fire_backtest_regen as R  # noqa: E402
from auto_trading.backtest.advanced_threshold_sweep import build_signals  # noqa: E402

COST = 0.2   # 왕복 거래비용 %


def run_rule(entries, max_hold, stop=None, activate=None, gap=None, floor=None):
    """실제 청산 로직(simulate_exit)에 상수를 갈아끼워 실행."""
    saved = (R.STOP_LOSS_RATE, R.ARMED_GIVEBACK_STOP, R.TRAIL_ACTIVATE_RATE,
             R.TRAIL_GAP, R.MIN_PROFIT_FLOOR)
    if stop is not None:
        R.STOP_LOSS_RATE = stop
        R.ARMED_GIVEBACK_STOP = stop
    if activate is not None:
        R.TRAIL_ACTIVATE_RATE = activate
    if gap is not None:
        R.TRAIL_GAP = gap
    if floor is not None:
        R.MIN_PROFIT_FLOOR = floor
    try:
        out = []
        for d, i, entry, ts in entries:
            res = R.simulate_exit(d, i, entry, max_hold)
            if res:
                out.append((ts, res['ret_pct']))
        return pd.DataFrame(out, columns=['D', 'ret'])
    finally:
        (R.STOP_LOSS_RATE, R.ARMED_GIVEBACK_STOP, R.TRAIL_ACTIVATE_RATE,
         R.TRAIL_GAP, R.MIN_PROFIT_FLOOR) = saved


def run_plain(entries, hold, stop=None, take=None, intraday=True):
    """단순 규칙: hold일 보유, 그 사이 손절/익절 터치 시 청산."""
    out = []
    for d, i, entry, ts in entries:
        last = min(i + hold, len(d) - 1)
        ret = None
        for j in range(i + 1, last + 1):
            if intraday:
                lo = float(d['저가'].iloc[j])
                hi = float(d['고가'].iloc[j])
                if stop is not None and (lo / entry - 1) <= stop:
                    ret = stop * 100
                    break
                if take is not None and (hi / entry - 1) >= take:
                    ret = take * 100
                    break
            else:
                r = float(d['종가'].iloc[j]) / entry - 1
                if stop is not None and r <= stop:
                    ret = r * 100
                    break
                if take is not None and r >= take:
                    ret = r * 100
                    break
        if ret is None:
            ret = (float(d['종가'].iloc[last]) / entry - 1) * 100
        out.append((ts, ret))
    return pd.DataFrame(out, columns=['D', 'ret'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', default='2023-04-01')
    ap.add_argument('--end', default='2026-08-12')
    ap.add_argument('--threshold', type=float, default=2.0)
    args = ap.parse_args()
    start, end = pd.Timestamp(args.start), pd.Timestamp(args.end)

    print(f'신호 재구성... {args.start} ~ {args.end}')
    rows, frames = build_signals(start, end)
    rows = [r for r in rows if r['chg'] >= args.threshold]
    entries = [(frames[r['code']][0], r['i'], r['close'], r['D']) for r in rows]
    print(f'신호 {len(entries):,}건\n')

    variants = [
        ('현행(트레일링,최대15일)', lambda: run_rule(entries, 15)),
        ('현행+최대5일', lambda: run_rule(entries, 5)),
        ('현행+최대3일', lambda: run_rule(entries, 3)),
        ('활성3%/gap3%/최대15일', lambda: run_rule(entries, 15, activate=0.03, gap=0.03)),
        ('활성3%/gap3%/최대5일', lambda: run_rule(entries, 5, activate=0.03, gap=0.03)),
        ('활성3%/gap3%/최대3일', lambda: run_rule(entries, 3, activate=0.03, gap=0.03)),
        ('단순 3일보유', lambda: run_plain(entries, 3)),
        ('단순 3일+손절6%', lambda: run_plain(entries, 3, stop=-0.06)),
        ('단순 3일+손절6%+익절7%', lambda: run_plain(entries, 3, stop=-0.06, take=0.07)),
        ('단순 5일+손절6%', lambda: run_plain(entries, 5, stop=-0.06)),
        ('단순 1일보유', lambda: run_plain(entries, 1)),
    ]

    results = {}
    for name, fn in variants:
        df = fn()
        df['y'] = df['D'].dt.year
        results[name] = df
        print(f'  계산 완료: {name}')

    years = sorted(results['현행(트레일링,최대15일)']['y'].unique())
    base = results['현행(트레일링,최대15일)']
    base_by_y = base.groupby('y')['ret'].mean()

    print()
    print('=' * 104)
    print(f'연도별 평균 수익률 % (비용 반영 전) — 개선안은 "모든 해"에서 현행보다 높아야 한다')
    print('=' * 104)
    print(f'{"청산 방식":<24}' + ''.join(f'{y:>11}' for y in years) +
          f'{"전체":>11}{"비용후":>10}{"현행상회":>10}')
    print('-' * 104)
    for name, _ in variants:
        df = results[name]
        by_y = df.groupby('y')['ret'].mean()
        beat = sum(1 for y in years if by_y.get(y, np.nan) > base_by_y.get(y, np.nan))
        allm = df['ret'].mean()
        mark = '  <= 현행' if name.startswith('현행(') else ''
        print(f'{name:<24}' + ''.join(f'{by_y.get(y, float("nan")):>11.3f}' for y in years) +
              f'{allm:>11.3f}{allm - COST:>10.3f}{beat:>7}/{len(years)}{mark}')

    print()
    print('=' * 104)
    print('승률 / 중앙값')
    print('=' * 104)
    print(f'{"청산 방식":<24}{"승률":>10}{"중앙값%":>11}{"표준편차":>11}')
    print('-' * 104)
    for name, _ in variants:
        df = results[name]
        print(f'{name:<24}{(df["ret"] > 0).mean() * 100:>9.1f}%'
              f'{df["ret"].median():>11.3f}{df["ret"].std():>11.2f}')


if __name__ == '__main__':
    main()
