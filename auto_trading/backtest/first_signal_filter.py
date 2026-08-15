# -*- coding: utf-8 -*-
"""첫 신호일(signal_days=1) 안에서 '데드캣'을 당일에 걸러낼 방법 찾기 (2026-08-14 작성).

배경: 신호 차수가 올라갈수록 성과가 단조 감소한다(1번째 +0.431% → 6번째 -0.697%).
      즉 '며칠 더 지켜보고 확인'하는 접근은 데이터가 두 번 연속 부정했다.
      그래서 기다리지 않고 '그날 안에' 판별 가능한 지표로 데드캣을 거르는 쪽을 찾는다.

당일에 알 수 있는 판별 후보
  종가위치   : (종가-저가)/(고가-저가). 낮으면 윗꼬리 — 장중 급등이 밀린 것 = 데드캣 징후
  갭         : 시가/전일종가. 갭상승 후 밀렸는지
  실체비율   : |종가-시가|/(고가-저가)
  직전5일    : 급락 후 반등인지, 이미 오른 상태인지
  거래대금비 : 당일/5일평균
  MA20 위치  : 종가가 MA20 위인지

기간 분할(전/후반기)로 같이 내서 한쪽 기간에만 통하는 조건을 걸러낸다.
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

from auto_trading.backtest.entry_timing import load_signals, CLUSTER_GAP  # noqa: E402
from auto_trading.backtest.fire_backtest_regen import load_ohlc  # noqa: E402

FWD = 3
SPLIT = pd.Timestamp('2026-02-28')


def build():
    sig = load_signals()
    recs = []
    for code, g in sig.groupby('code'):
        o = load_ohlc(code)
        if o is None or len(o) < 30:
            continue
        raw = None
        path = None
        g = g.sort_values('D')
        gap = g['D'].diff().dt.days
        cluster = (gap.isna() | (gap > CLUSTER_GAP)).cumsum()
        ma20 = o['종가'].rolling(20).mean()
        for cid, cg in g.assign(cluster=cluster).groupby('cluster'):
            r = cg.iloc[0]                      # 첫 신호일만
            i = o.index.searchsorted(r['D'])
            if i >= len(o) or o.index[i] != r['D'] or i < 21:
                continue
            c = float(o['종가'].iloc[i]); h = float(o['고가'].iloc[i])
            lo = float(o['저가'].iloc[i]); op = float(o['시가'].iloc[i])
            prev = float(o['종가'].iloc[i - 1])
            j = i + FWD
            if c <= 0 or h <= lo or j >= len(o):
                continue
            lows = o['저가'].iloc[i + 1:i + 1 + FWD]
            recs.append({
                'D': r['D'],
                'code': code,
                'entry': c,                                # 진입가(그날 종가)
                'close_pos': (c - lo) / (h - lo),          # 1=고가마감, 0=저가마감
                'gap': (op / prev - 1) * 100,
                'body': abs(c - op) / (h - lo),
                'prior5': (prev / float(o['종가'].iloc[i - 6]) - 1) * 100,
                'tvr': (r['tv'] / r['avg5tv'] * 100) if r['avg5tv'] else np.nan,
                'above_ma20': c > float(ma20.iloc[i]) if np.isfinite(ma20.iloc[i]) else np.nan,
                'chg': r['chg'],
                'ret': (float(o['종가'].iloc[j]) / c - 1) * 100,
                'mdd': (float(lows.min()) / c - 1) * 100 if len(lows) else np.nan,
            })
    return pd.DataFrame(recs).dropna(subset=['ret'])


def main():
    X = build()
    H1, H2 = X[X['D'] <= SPLIT], X[X['D'] > SPLIT]
    print(f'첫 신호일 표본 {len(X):,}건 (전반기 {len(H1):,} / 후반기 {len(H2):,})')
    print(f'기준선: 전체 {X["ret"].mean():+.3f}% / 전반기 {H1["ret"].mean():+.3f}% / '
          f'후반기 {H2["ret"].mean():+.3f}%\n')

    def tbl(title, groups):
        print('=' * 92)
        print(title)
        print('=' * 92)
        print(f'{"구분":<22}{"건수":>8}{"전체%":>9}{"중앙%":>9}{"승률":>8}'
              f'{"MDD%":>8}{"전반기%":>9}{"후반기%":>9}')
        print('-' * 92)
        for lab, fn in groups:
            a, b, c = fn(X), fn(H1), fn(H2)
            if len(a) < 150:
                print(f'{lab:<22}{len(a):>8,}   (표본부족)')
                continue
            print(f'{lab:<22}{len(a):>8,}{a["ret"].mean():>9.3f}{a["ret"].median():>9.3f}'
                  f'{(a["ret"] > 0).mean() * 100:>7.1f}%{a["mdd"].mean():>8.2f}'
                  f'{b["ret"].mean() if len(b) > 50 else float("nan"):>9.3f}'
                  f'{c["ret"].mean() if len(c) > 50 else float("nan"):>9.3f}')
        print()

    tbl('1. 종가위치 — 낮을수록 윗꼬리(장중 급등이 밀림) = 데드캣 징후',
        [('0.0~0.3 (윗꼬리 큼)', lambda d: d[d['close_pos'] < 0.3]),
         ('0.3~0.6', lambda d: d[(d['close_pos'] >= 0.3) & (d['close_pos'] < 0.6)]),
         ('0.6~0.85', lambda d: d[(d['close_pos'] >= 0.6) & (d['close_pos'] < 0.85)]),
         ('0.85~1.0 (고가 마감)', lambda d: d[d['close_pos'] >= 0.85])])

    tbl('2. 갭 (시가/전일종가)',
        [('갭하락 (<0%)', lambda d: d[d['gap'] < 0]),
         ('0~2%', lambda d: d[(d['gap'] >= 0) & (d['gap'] < 2)]),
         ('2~5%', lambda d: d[(d['gap'] >= 2) & (d['gap'] < 5)]),
         ('5%↑', lambda d: d[d['gap'] >= 5])])

    tbl('3. 직전 5일 상태',
        [('급락 -10%↓', lambda d: d[d['prior5'] <= -10]),
         ('하락 -10~-3%', lambda d: d[(d['prior5'] > -10) & (d['prior5'] <= -3)]),
         ('보합 -3~+3%', lambda d: d[(d['prior5'] > -3) & (d['prior5'] < 3)]),
         ('상승 +3~+10%', lambda d: d[(d['prior5'] >= 3) & (d['prior5'] < 10)]),
         ('급등 +10%↑', lambda d: d[d['prior5'] >= 10])])

    tbl('4. MA20 위치',
        [('MA20 위', lambda d: d[d['above_ma20'] == True]),      # noqa: E712
         ('MA20 아래', lambda d: d[d['above_ma20'] == False])])  # noqa: E712

    tbl('5. 거래대금비',
        [('100% 미만', lambda d: d[d['tvr'] < 100]),
         ('100~150%', lambda d: d[(d['tvr'] >= 100) & (d['tvr'] < 150)]),
         ('150~300%', lambda d: d[(d['tvr'] >= 150) & (d['tvr'] < 300)]),
         ('300%↑', lambda d: d[d['tvr'] >= 300])])

    tbl('6. 조합 — 양 기간 모두 살아남는 조건 찾기',
        [('종가위치>=0.6', lambda d: d[d['close_pos'] >= 0.6]),
         ('  + MA20 위', lambda d: d[(d['close_pos'] >= 0.6) & (d['above_ma20'] == True)]),  # noqa: E712
         ('  + 대금비<300', lambda d: d[(d['close_pos'] >= 0.6) & (d['tvr'] < 300)]),
         ('  + 둘 다', lambda d: d[(d['close_pos'] >= 0.6) & (d['above_ma20'] == True)  # noqa: E712
                                   & (d['tvr'] < 300)])])


if __name__ == '__main__':
    main()
