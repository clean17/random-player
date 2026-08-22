# -*- coding: utf-8 -*-
"""시장 레짐 게이트 검증 (2026-08-14 작성).

regime_test_3y.py 결과: 신호는 상승장 +0.598% / 하락장 -0.808%로 시장을 거의 그대로 따라간다
(알파 ≈ 0). 즉 개선 여지는 '하락장에 안 사는 것'에 있다. 어떤 레짐 지표로 그게 되는지 검증한다.

⚠️ 핵심 함정: 레짐은 '그날 매수 시점에 알 수 있는 값'이어야 한다. 그 달이 하락장이었는지는
   나중에야 아는 것이라, 사후 정보로 거르면 당연히 좋아 보이지만 실제로는 쓸 수 없다.
   그래서 모든 지표를 '전일까지의 데이터'로만 계산한다.

검증 지표:
  breadth   : 전 종목 중 (종가 > MA20) 비율 — 현재 코드의 BREADTH_MIN이 쓰는 값
  mkt_ma    : 시장 평균지수(전 종목 동일가중)가 자기 MA20 위인지
  mkt_ret5  : 시장 평균지수의 최근 5거래일 수익률
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

from auto_trading.backtest.advanced_threshold_sweep import build_signals  # noqa: E402

HOLD = 3
COST = 0.2   # 왕복 거래비용 %


def build_regime(frames, start, end):
    """전일까지의 정보로만 계산한 일자별 레짐 지표."""
    closes = {}
    for code, (d, _m) in frames.items():
        closes[code] = d['종가'].astype(float)
    px = pd.DataFrame(closes).sort_index()
    px = px[(px.index >= start - pd.Timedelta(days=40)) & (px.index <= end)]

    ma20 = px.rolling(20).mean()
    above = (px > ma20)
    breadth = above.sum(axis=1) / px.notna().sum(axis=1)

    idx = px.pct_change().mean(axis=1).add(1).cumprod()      # 동일가중 시장지수
    idx_ma20 = idx.rolling(20).mean()
    mkt_ma = idx > idx_ma20
    mkt_ret5 = idx.pct_change(5) * 100

    # 매수 시점에 쓰려면 '전일까지' 값이어야 한다 → 한 칸 shift
    return pd.DataFrame({
        'breadth': breadth.shift(1),
        'mkt_ma': mkt_ma.shift(1),
        'mkt_ret5': mkt_ret5.shift(1),
    })


def report(label, sub, total_n, mark=''):
    if len(sub) == 0:
        print(f'{label:<28}{"거래없음":>10}')
        return
    net = sub['ret'] - COST
    print(f'{label:<28}{len(sub):>8,}{len(sub) / total_n * 100:>7.0f}%'
          f'{sub["ret"].mean():>10.3f}{net.mean():>10.3f}'
          f'{(sub["ret"] > 0).mean() * 100:>8.1f}%'
          f'{sub["ret"].sum() / 100:>11.1f}{mark}')


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

    for r in rows:
        d, _ = frames[r['code']]
        j = r['i'] + HOLD
        r['ret'] = (float(d['종가'].iloc[j]) / r['close'] - 1) * 100 if j < len(d) else np.nan
    sig = pd.DataFrame([r for r in rows if np.isfinite(r.get('ret', np.nan))])
    print(f'신호 {len(sig):,}건\n')

    reg = build_regime(frames, start, end)
    sig = sig.join(reg, on='D')
    sig = sig.dropna(subset=['breadth'])
    n = len(sig)

    hdr = (f'{"게이트":<28}{"거래수":>8}{"비중":>8}{"평균%":>10}{"비용후%":>10}'
           f'{"승률":>8}{"누적(배수합)":>12}')

    print('=' * 90)
    print(f'A. breadth 게이트 (종가>MA20 비율이 X 이상일 때만 매수) — 왕복비용 {COST}% 반영')
    print('=' * 90)
    print(hdr)
    print('-' * 90)
    report('게이트 없음(현재)', sig, n, '  <= 현재')
    for th in (0.30, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65):
        report(f'breadth >= {th:.0%}', sig[sig['breadth'] >= th], n)

    print()
    print('=' * 90)
    print('B. 다른 레짐 지표')
    print('=' * 90)
    print(hdr)
    print('-' * 90)
    report('시장지수 > MA20', sig[sig['mkt_ma'] == True], n)  # noqa: E712
    for th in (-2, -1, 0, 1):
        report(f'시장 5일수익률 >= {th}%', sig[sig['mkt_ret5'] >= th], n)

    print()
    print('=' * 90)
    print('C. 조합')
    print('=' * 90)
    print(hdr)
    print('-' * 90)
    report('breadth>=50% & 지수>MA20', sig[(sig['breadth'] >= 0.5) & (sig['mkt_ma'] == True)], n)  # noqa: E712
    report('breadth>=55% & 5일>=0%', sig[(sig['breadth'] >= 0.55) & (sig['mkt_ret5'] >= 0)], n)
    report('breadth>=45% & 5일>=-1%', sig[(sig['breadth'] >= 0.45) & (sig['mkt_ret5'] >= -1)], n)

    print()
    print('=' * 96)
    print('D. 연도별 검증 — 게이트가 특정 해에만 통하는 건 아닌지 (과최적화 판별)')
    print('=' * 96)
    sig['y'] = sig['D'].dt.year
    gates = [
        ('게이트없음', lambda s: s),
        ('breadth>=40%', lambda s: s[s['breadth'] >= 0.40]),
        ('breadth>=55%', lambda s: s[s['breadth'] >= 0.55]),
        ('지수>MA20', lambda s: s[s['mkt_ma'] == True]),          # noqa: E712
        ('시장5일>=0%', lambda s: s[s['mkt_ret5'] >= 0]),
        ('시장5일>=1%', lambda s: s[s['mkt_ret5'] >= 1]),
    ]
    years = sorted(sig['y'].unique())
    print(f'{"게이트":<16}' + ''.join(f'{y:>12}' for y in years) + f'{"전체":>12}{"플러스해":>10}')
    print('-' * 96)
    for name, fn in gates:
        cells, pos = [], 0
        for y in years:
            sub = fn(sig[sig['y'] == y])
            m = sub['ret'].mean() if len(sub) else float('nan')
            cells.append(f'{m:>12.3f}')
            if np.isfinite(m) and m > 0:
                pos += 1
        allm = fn(sig)['ret'].mean()
        print(f'{name:<16}' + ''.join(cells) + f'{allm:>12.3f}{pos:>7}/{len(years)}')

    print()
    print('※ 위는 비용 반영 전. 왕복비용 0.2%를 빼면 각 칸에서 0.2%p씩 내려간다.')
    print('  게이트가 진짜라면 모든 해에서 "게이트없음"보다 높아야 한다.')


if __name__ == '__main__':
    main()
