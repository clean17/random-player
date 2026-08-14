# -*- coding: utf-8 -*-
"""청산 '방식' 비교 — 장중 트리거 vs 종가 판정 vs 단순 보유 (2026-08-14 작성).

앞선 스윕(exit_param_sweep.py)에서 손절선을 넓혀도 나빠지고, 오히려 빨리 나가는 쪽이 나았다.
한편 pnl_decomposition.py에서는 '그냥 3거래일 보유'가 +0.090%로 어떤 규칙보다 나았다.

차이의 후보: 현재 규칙은 30초 폴링이라 장중 고가/저가에 반응한다(백테스트도 고가/저가로 재현).
반면 '3일 보유'는 종가 기준이다. 즉 장중 노이즈에 손절이 털리고(휩쏘) 종가에는 회복하는
패턴이면, 같은 손절선이라도 '종가로만 판정'하면 결과가 달라져야 한다. 그걸 직접 잰다.

비교 대상
  A. 단순 보유      : N거래일 뒤 종가에 전량
  B. 종가 손절      : 매일 종가로만 판정, rate <= stop 이면 다음날 시가 아닌 그 종가에 전량
  C. 장중 손절      : 저가가 stop을 건드리면 그 가격에 전량 (현재 방식에 해당)
  D. 종가 손절+익절 : 종가 판정 + rate >= take 이면 전량
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

from auto_trading.backtest.fire_backtest_regen import load_ohlc  # noqa: E402

SPLIT = pd.Timestamp('2026-04-30')


def sim(ohlc, i, entry, hold, stop=None, take=None, intraday=False):
    """진입 다음날부터 hold일까지 판정. 반환: 수익률%"""
    last = min(i + hold, len(ohlc) - 1)
    for j in range(i + 1, last + 1):
        c = float(ohlc['종가'].iloc[j])
        if intraday:
            lo, hi = float(ohlc['저가'].iloc[j]), float(ohlc['고가'].iloc[j])
            if stop is not None and (lo / entry - 1) <= stop:
                return stop * 100          # 손절가에 체결됐다고 가정
            if take is not None and (hi / entry - 1) >= take:
                return take * 100
        else:
            r = c / entry - 1
            if stop is not None and r <= stop:
                return r * 100
            if take is not None and r >= take:
                return r * 100
    return (float(ohlc['종가'].iloc[last]) / entry - 1) * 100


def report(label, vals, dates, mark=''):
    s = pd.Series(vals)
    d = pd.Series(dates)
    tr, te = s[d <= SPLIT], s[d > SPLIT]
    print(f'{label:<30}{s.mean():>9.3f}{s.median():>9.3f}{(s > 0).mean() * 100:>8.1f}%'
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
        o = load_ohlc(code)
        if o is None:
            continue
        i = o.index.searchsorted(d)
        if i >= len(o) or o.index[i] != d:
            continue
        entries.append((o, i, float(o['종가'].iloc[i]), d))
    print(f'신호 {len(entries):,}건\n')
    dates = [e[3] for e in entries]

    hdr = f'{"방식":<30}{"평균%":>9}{"중앙%":>9}{"승률":>8}{"train%":>9}{"test%":>9}'

    print('=' * 82)
    print('A. 단순 보유 (종가 청산, 규칙 없음)')
    print('=' * 82)
    print(hdr)
    print('-' * 82)
    for h in (1, 2, 3, 5):
        report(f'{h}일 보유', [sim(o, i, e, h) for o, i, e, _ in entries], dates)

    print()
    print('=' * 82)
    print('B/C. 같은 손절선을 종가로 판정 vs 장중(고저가)로 판정 — 3일 보유')
    print('=' * 82)
    print(hdr)
    print('-' * 82)
    for stop in (-0.04, -0.06, -0.10):
        report(f'종가손절 {stop:.0%} (3일)',
               [sim(o, i, e, 3, stop=stop) for o, i, e, _ in entries], dates)
        report(f'장중손절 {stop:.0%} (3일)',
               [sim(o, i, e, 3, stop=stop, intraday=True) for o, i, e, _ in entries], dates,
               '  <= 현재 방식' if stop == -0.06 else '')

    print()
    print('=' * 82)
    print('D. 종가 판정 + 익절 조합 (3일 보유)')
    print('=' * 82)
    print(hdr)
    print('-' * 82)
    for stop, take in [(-0.06, 0.03), (-0.06, 0.05), (-0.06, 0.07),
                       (-0.10, 0.05), (-0.04, 0.03), (None, 0.03), (None, 0.05)]:
        s_lbl = '없음' if stop is None else f'{stop:.0%}'
        report(f'종가 손절{s_lbl}/익절+{take:.0%}',
               [sim(o, i, e, 3, stop=stop, take=take) for o, i, e, _ in entries], dates)

    print()
    print('=' * 82)
    print('E. 장중 익절만 (손절 없음) — 오르면 바로 먹고 나오기')
    print('=' * 82)
    print(hdr)
    print('-' * 82)
    for h in (2, 3, 5):
        for take in (0.03, 0.05, 0.07):
            report(f'{h}일/장중익절+{take:.0%}',
                   [sim(o, i, e, h, take=take, intraday=True) for o, i, e, _ in entries], dates)


if __name__ == '__main__':
    main()
