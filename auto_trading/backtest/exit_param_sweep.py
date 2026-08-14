# -*- coding: utf-8 -*-
"""청산 파라미터 스윕 (2026-08-14 작성).

pnl_decomposition.py에서 '진입 신호는 거의 보합(3일 보유 +0.09%)인데 현재 청산 규칙을 씌우면
-0.69%'라는 결과가 나왔다. 즉 손실의 주범이 청산 규칙이다. 어떤 값이 덜 깎는지 찾는다.

보유 15일 내 최고/최저 도달폭이 중앙값 +13.9% / -14.8%라 종목이 평소 ±14%씩 흔들린다.
현재 손절 -6%는 그 진폭 한참 안쪽이라 흔들림에 털리고 나서 회복하는 패턴이 의심된다.

사용법:
    venv/Scripts/python.exe auto_trading/backtest/exit_param_sweep.py
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

MAX_HOLD = 15
SPLIT = pd.Timestamp('2026-04-30')


def run(entries, stop=None, activate=None, gap=None, floor=None, stall=None):
    """상수를 임시로 갈아끼우고 전 신호에 청산 시뮬레이션을 돌린다."""
    saved = (R.STOP_LOSS_RATE, R.ARMED_GIVEBACK_STOP, R.TRAIL_ACTIVATE_RATE,
             R.TRAIL_GAP, R.MIN_PROFIT_FLOOR, R.STALL_GAP)
    if stop is not None:
        R.STOP_LOSS_RATE = stop
        R.ARMED_GIVEBACK_STOP = stop
    if activate is not None:
        R.TRAIL_ACTIVATE_RATE = activate
    if gap is not None:
        R.TRAIL_GAP = gap
    if floor is not None:
        R.MIN_PROFIT_FLOOR = floor
    if stall is not None:
        R.STALL_GAP = stall
    try:
        out = []
        for code, i, entry, d in entries:
            ohlc = R._pkl_cache.get(code)
            res = R.simulate_exit(ohlc, i, entry, MAX_HOLD)
            if res:
                out.append((d, res['ret_pct'], res['exit']))
        return pd.DataFrame(out, columns=['D', 'ret', 'exit'])
    finally:
        (R.STOP_LOSS_RATE, R.ARMED_GIVEBACK_STOP, R.TRAIL_ACTIVATE_RATE,
         R.TRAIL_GAP, R.MIN_PROFIT_FLOOR, R.STALL_GAP) = saved


def line(label, df, mark=''):
    tr = df[df['D'] <= SPLIT]['ret']
    te = df[df['D'] > SPLIT]['ret']
    stop_pct = (df['exit'] == 'stop_loss').mean() * 100
    print(f'{label:<26}{len(df):>7,}{df["ret"].mean():>9.3f}{df["ret"].median():>9.3f}'
          f'{(df["ret"] > 0).mean() * 100:>7.1f}%{stop_pct:>8.1f}%'
          f'{tr.mean():>9.3f}{te.mean():>9.3f}{mark}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', default='logs/kiwoom_trading/fire_backtest_result_current.csv')
    args = ap.parse_args()

    sig = pd.read_csv(args.csv, encoding='utf-8-sig')
    sig['D'] = pd.to_datetime(sig['D'])
    sig['code'] = sig['code'].astype(str).str.zfill(6)

    entries = []
    for code, d in zip(sig['code'], sig['D']):
        ohlc = R.load_ohlc(code)
        if ohlc is None:
            continue
        i = ohlc.index.searchsorted(d)
        if i >= len(ohlc) or ohlc.index[i] != d:
            continue
        entries.append((code, i, float(ohlc['종가'].iloc[i]), d))
    print(f'신호 {len(entries):,}건\n')

    hdr = (f'{"설정":<26}{"건수":>7}{"평균%":>9}{"중앙%":>9}{"승률":>8}{"손절비중":>9}'
           f'{"train%":>9}{"test%":>9}')

    print('=' * 96)
    print('1) 손절선(STOP_LOSS_RATE) 스윕 — 나머지는 현행 유지')
    print('=' * 96)
    print(hdr)
    print('-' * 96)
    for s in (-0.04, -0.06, -0.08, -0.10, -0.12, -0.15, -0.20, -0.99):
        lbl = '손절 없음(-99%)' if s == -0.99 else f'손절 {s:.0%}'
        line(lbl, run(entries, stop=s), '  <= 현재' if s == -0.06 else '')

    print()
    print('=' * 96)
    print('2) 트레일링 gap 스윕 (손절은 현행 -6% 고정)')
    print('=' * 96)
    print(hdr)
    print('-' * 96)
    for g in (0.03, 0.05, 0.07, 0.10, 0.15):
        line(f'gap {g:.0%}', run(entries, gap=g), '  <= 현재' if g == 0.05 else '')

    print()
    print('=' * 96)
    print('3) 트레일링 활성 시점 스윕 (손절 -6%, gap 5% 고정)')
    print('=' * 96)
    print(hdr)
    print('-' * 96)
    for a in (0.03, 0.05, 0.07, 0.10, 0.15):
        line(f'활성 +{a:.0%}', run(entries, activate=a), '  <= 현재' if a == 0.07 else '')

    print()
    print('=' * 96)
    print('4) 조합 후보 — 손절을 넓히고 트레일링도 같이 조정')
    print('=' * 96)
    print(hdr)
    print('-' * 96)
    line('현행(-6/+7/5)', run(entries), '  <= 현재')
    for s, a, g in [(-0.10, 0.07, 0.05), (-0.10, 0.05, 0.07), (-0.12, 0.07, 0.07),
                    (-0.15, 0.10, 0.10), (-0.99, 0.07, 0.05), (-0.99, 0.10, 0.10)]:
        s_lbl = '없음' if s == -0.99 else f'{s:.0%}'
        line(f'손절{s_lbl}/활성+{a:.0%}/gap{g:.0%}', run(entries, stop=s, activate=a, gap=g))


if __name__ == '__main__':
    main()
