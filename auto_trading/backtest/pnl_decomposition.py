# -*- coding: utf-8 -*-
"""손실이 '진입 신호' 탓인지 '청산 규칙' 탓인지 분해한다 (2026-08-14 작성).

계기: "관심 종목은 실제로 계속 오르는데 왜 백테스트는 마이너스인가?
      insert(신호 생성)/select(후보 선정)/트레일링 스탑 중 무엇을 고쳐야 하나?"

같은 신호 집합에 대해 두 가지를 나란히 잰다.
  A. 그냥 N거래일 보유 (청산 규칙 없음)  → 진입 신호 자체의 예측력
  B. 현재 청산 규칙 적용                 → 트레일링/손절이 A를 얼마나 깎거나 살리는지

A가 플러스인데 B가 마이너스면 문제는 신호가 아니라 청산 규칙이다.
A도 마이너스면 신호부터 손봐야 한다.
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

from auto_trading.backtest.fire_backtest_regen import load_ohlc, simulate_exit  # noqa: E402

HORIZONS = [1, 2, 3, 5, 10, 20]
MAX_HOLD = 15


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', default='logs/kiwoom_trading/fire_backtest_result_current.csv')
    args = ap.parse_args()

    sig = pd.read_csv(args.csv, encoding='utf-8-sig')
    sig['D'] = pd.to_datetime(sig['D'])
    sig['code'] = sig['code'].astype(str).str.zfill(6)
    print(f'신호 {len(sig):,}건 / {sig["D"].dt.date.nunique()}거래일 '
          f'({sig["D"].min().date()} ~ {sig["D"].max().date()})\n')

    recs = []
    for code, d, ret_rule in zip(sig['code'], sig['D'], sig['ret_pct']):
        ohlc = load_ohlc(code)
        if ohlc is None:
            continue
        i = ohlc.index.searchsorted(d)
        if i >= len(ohlc) or ohlc.index[i] != d:
            continue
        entry = float(ohlc['종가'].iloc[i])
        if entry <= 0:
            continue
        row = {'code': code, 'D': d, 'rule': ret_rule}
        for h in HORIZONS:
            j = i + h
            row[f'h{h}'] = (float(ohlc['종가'].iloc[j]) / entry - 1) * 100 if j < len(ohlc) else np.nan
        # 보유기간 중 최고가/최저가 (규칙이 잡을 수 있었던 상단/하단)
        hi = ohlc['고가'].iloc[i + 1:i + 1 + MAX_HOLD]
        lo = ohlc['저가'].iloc[i + 1:i + 1 + MAX_HOLD]
        row['max_up'] = (float(hi.max()) / entry - 1) * 100 if len(hi) else np.nan
        row['max_dn'] = (float(lo.min()) / entry - 1) * 100 if len(lo) else np.nan
        recs.append(row)

    df = pd.DataFrame(recs)
    print(f'매칭 성공 {len(df):,}건\n')

    split = pd.Timestamp('2026-04-30')
    print('=' * 84)
    print('A. 진입 신호 자체 — 청산 규칙 없이 그냥 N거래일 보유했다면')
    print('=' * 84)
    print(f'{"보유기간":<12}{"평균%":>10}{"중앙%":>10}{"승률":>9}{"train%":>10}{"test%":>10}')
    print('-' * 84)
    for h in HORIZONS:
        c = df[f'h{h}'].dropna()
        tr = df[df['D'] <= split][f'h{h}'].dropna()
        te = df[df['D'] > split][f'h{h}'].dropna()
        print(f'{f"{h}거래일":<12}{c.mean():>10.3f}{c.median():>10.3f}'
              f'{(c > 0).mean() * 100:>8.1f}%{tr.mean():>10.3f}{te.mean():>10.3f}')

    print()
    print('=' * 84)
    print('B. 현재 청산 규칙 적용 결과 (손절 -6% / 트레일링 활성 +7% gap 5% / 최소이익 3%)')
    print('=' * 84)
    r = df['rule'].dropna()
    tr = df[df['D'] <= split]['rule'].dropna()
    te = df[df['D'] > split]['rule'].dropna()
    print(f'{"규칙적용":<12}{r.mean():>10.3f}{r.median():>10.3f}'
          f'{(r > 0).mean() * 100:>8.1f}%{tr.mean():>10.3f}{te.mean():>10.3f}')

    print()
    print('=' * 84)
    print('C. 규칙이 얼마나 깎았나 (같은 신호, 3거래일 보유 대비)')
    print('=' * 84)
    both = df.dropna(subset=['h3', 'rule'])
    diff = both['rule'] - both['h3']
    print(f'  3거래일 그냥 보유 : {both["h3"].mean():+.3f}%')
    print(f'  현재 규칙 적용    : {both["rule"].mean():+.3f}%')
    print(f'  규칙의 기여       : {diff.mean():+.3f}%p  '
          f'(규칙이 더 나은 경우 {(diff > 0).mean() * 100:.1f}%)')

    print()
    print('=' * 84)
    print('D. 기회는 있었나 — 보유 15일 내 최고/최저 도달폭')
    print('=' * 84)
    print(f'  진입 후 최고가까지 평균 {df["max_up"].mean():+.2f}% (중앙 {df["max_up"].median():+.2f}%)')
    print(f'  진입 후 최저가까지 평균 {df["max_dn"].mean():+.2f}% (중앙 {df["max_dn"].median():+.2f}%)')
    for th in (3, 5, 7, 10, 15):
        print(f'    +{th}% 이상 올라간 적 있는 비율: {(df["max_up"] >= th).mean() * 100:5.1f}%   '
              f'-{th}% 이하로 내려간 적 있는 비율: {(df["max_dn"] <= -th).mean() * 100:5.1f}%')


if __name__ == '__main__':
    main()
