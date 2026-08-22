# -*- coding: utf-8 -*-
"""3년치 장세별 검증 (2026-08-14 작성).

검증할 주장:
  "장이 안 좋아도 올라가려는 종목은 있다. 그런 종목만 사면 수익이 작을 순 있어도 손해는 안 난다."

방법:
  interest_stocks DB는 1년치뿐이라 pkl 일봉으로 신호를 3년+ 재구성한다(조건은
  advanced_threshold_sweep.py와 동일 — 2_finding_stocks_advanced.py 재현).
  각 신호의 N거래일 보유 수익률을 구하고, 같은 날 시장 전체 평균과 나란히 놓아
  '장세(상승월/하락월)'별로 나눠 본다.

⚠️ 생존 편향: pkl에는 현재 상장된 종목만 있다. 상장폐지·거래정지된 종목이 빠져 있어
   실제보다 결과가 좋게 나온다. 즉 아래 수치는 낙관 쪽으로 치우친 상한선이다.
"""
import argparse
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from auto_trading.backtest.advanced_threshold_sweep import build_signals  # noqa: E402
from auto_trading.backtest.fire_backtest_regen import load_ohlc  # noqa: E402

HOLD = 3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', default='2023-04-01')
    ap.add_argument('--end', default='2026-08-12')
    ap.add_argument('--threshold', type=float, default=2.0, help='당일 등락률 하한')
    args = ap.parse_args()
    start, end = pd.Timestamp(args.start), pd.Timestamp(args.end)

    print(f'신호 재구성 중... {args.start} ~ {args.end} (등락률 하한 {args.threshold}%)')
    rows, frames = build_signals(start, end)
    rows = [r for r in rows if r['chg'] >= args.threshold]
    print(f'신호 {len(rows):,}건\n')

    # 신호별 N일 보유 수익률
    for r in rows:
        d, _ = frames[r['code']]
        i = r['i']
        j = i + HOLD
        r['ret'] = (float(d['종가'].iloc[j]) / r['close'] - 1) * 100 if j < len(d) else np.nan
    sig = pd.DataFrame([r for r in rows if np.isfinite(r.get('ret', np.nan))])

    # 시장 전체 대조군 — 같은 프레임을 재사용(추가 I/O 없음)
    mrows = []
    for code, (d, _mkt) in frames.items():
        c = d['종가'].astype(float)
        fwd = (c.shift(-HOLD) / c - 1) * 100
        for ts, v in fwd.items():
            if start <= ts <= end and np.isfinite(v):
                mrows.append((ts, v))
    mkt = pd.DataFrame(mrows, columns=['D', 'ret'])

    sig['m'] = sig['D'].dt.to_period('M')
    mkt['m'] = mkt['D'].dt.to_period('M')
    mkt_by_m = mkt.groupby('m')['ret'].mean()

    print('=' * 96)
    print(f'월별 — 신호({HOLD}일 보유) vs 시장 전체({HOLD}일 보유)')
    print('=' * 96)
    print(f'{"월":<10}{"신호건수":>8}{"신호%":>9}{"시장%":>9}{"알파%p":>9}{"신호승률":>9}{"장세":>8}')
    print('-' * 96)
    recs = []
    for m in sorted(sig['m'].unique()):
        a = sig[sig['m'] == m]['ret']
        b = mkt_by_m.get(m, np.nan)
        if not np.isfinite(b):
            continue
        regime = '상승장' if b > 0 else '하락장'
        recs.append({'m': m, 'n': len(a), 'sig': a.mean(), 'mkt': b,
                     'alpha': a.mean() - b, 'win': (a > 0).mean() * 100, 'regime': regime})
        print(f'{str(m):<10}{len(a):>8,}{a.mean():>9.3f}{b:>9.3f}{a.mean() - b:>9.3f}'
              f'{(a > 0).mean() * 100:>8.1f}%{regime:>8}')

    R = pd.DataFrame(recs)
    print()
    print('=' * 96)
    print('장세별 집계 — 핵심 질문: 하락장에서도 신호가 플러스인가?')
    print('=' * 96)
    print(f'{"장세":<10}{"개월":>6}{"신호건수":>10}{"신호평균%":>11}{"시장평균%":>11}'
          f'{"알파%p":>9}{"신호가 플러스인 달":>18}')
    print('-' * 96)
    for regime in ('상승장', '하락장'):
        sub = R[R['regime'] == regime]
        if len(sub) == 0:
            continue
        months = sorted(sub['m'])
        allsig = sig[sig['m'].isin(months)]['ret']
        wm = np.average(sub['mkt'], weights=sub['n'])
        print(f'{regime:<10}{len(sub):>6}{int(sub["n"].sum()):>10,}{allsig.mean():>11.3f}'
              f'{wm:>11.3f}{allsig.mean() - wm:>9.3f}'
              f'{int((sub["sig"] > 0).sum()):>10}/{len(sub):<8}')

    print()
    total_sig = sig['ret'].mean()
    total_mkt = mkt['ret'].mean()
    print(f'전체: 신호 {total_sig:+.3f}% / 시장 {total_mkt:+.3f}% / 알파 {total_sig - total_mkt:+.3f}%p')
    print(f'      신호 승률 {(sig["ret"] > 0).mean() * 100:.1f}% / '
          f'시장 승률 {(mkt["ret"] > 0).mean() * 100:.1f}%')
    print(f'      플러스인 달 {int((R["sig"] > 0).sum())}/{len(R)}개월, '
          f'알파 플러스인 달 {int((R["alpha"] > 0).sum())}/{len(R)}개월')

    print()
    print('=' * 96)
    print('연도별')
    print('=' * 96)
    sig['y'] = sig['D'].dt.year
    mkt['y'] = mkt['D'].dt.year
    print(f'{"연도":<8}{"신호건수":>10}{"신호%":>10}{"시장%":>10}{"알파%p":>10}{"승률":>9}')
    print('-' * 96)
    for y in sorted(sig['y'].unique()):
        a = sig[sig['y'] == y]['ret']
        b = mkt[mkt['y'] == y]['ret'].mean()
        print(f'{y:<8}{len(a):>10,}{a.mean():>10.3f}{b:>10.3f}{a.mean() - b:>10.3f}'
              f'{(a > 0).mean() * 100:>8.1f}%')


if __name__ == '__main__':
    main()
