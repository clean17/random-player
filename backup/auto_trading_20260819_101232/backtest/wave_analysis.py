# -*- coding: utf-8 -*-
"""'주가는 파도처럼 며칠 오르고 며칠 내린다 → 다시 올라가기 시작할 때 사자' 가설 검증
(2026-08-14 작성).

검증할 것
  A. 파도(연속 상승/하락 구간)가 실제로 존재하는가 — 무작위(동전던지기)와 다른가?
  B. 일간 수익률에 자기상관이 있는가 (추세 지속 vs 평균회귀)
  C. 핵심: '하락 후 반등'(전환)과 '상승 지속'(추격) 중 어느 쪽이 더 버는가?
     현재 fire 신호는 '추격' 쪽이다(최근 오른 종목 중 오늘 오른 것을 산다).

pkl 전 종목 일봉을 직접 쓴다. interest_stocks 구조와 무관하게 원데이터로 판정한다.

⚠️ 생존 편향: pkl에는 현재 상장된 종목만 있다. 상장폐지분이 빠져 결과가 낙관 쪽이다.
"""
import argparse
import os
import sys
import glob

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

PKL_DIR = r'C:\my-project\AutoSales.py\data\pickle'
MIN_TRADING_VALUE = 2_000_000_000   # 거래대금 20억 — 실제로 살 수 있는 종목만


def load_all(start):
    """전 종목 일봉을 하나의 long-form 프레임으로."""
    frames = []
    for path in sorted(glob.glob(os.path.join(PKL_DIR, '*.pkl'))):
        try:
            df = pd.read_pickle(path)
        except Exception:
            continue
        if df is None or len(df) < 60 or '종가' not in df.columns or '거래량' not in df.columns:
            continue
        if not isinstance(df.index, pd.DatetimeIndex):
            continue
        d = df[df.index >= start]
        if len(d) < 60:
            continue
        c = d['종가'].astype(float)
        out = pd.DataFrame({
            'code': os.path.basename(path)[:6],
            'close': c,
            'tv': c * d['거래량'].astype(float),
        })
        out['ret'] = c.pct_change() * 100
        frames.append(out)
    return pd.concat(frames)


def run_lengths(sign_series):
    """연속 동일부호 구간 길이 목록."""
    s = sign_series.dropna()
    if len(s) == 0:
        return []
    grp = (s != s.shift()).cumsum()
    return s.groupby(grp).size().tolist()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', default='2023-01-01')
    args = ap.parse_args()
    start = pd.Timestamp(args.start)

    print(f'pkl 로드 중... (>= {args.start})')
    df = load_all(start)
    print(f'{df["code"].nunique():,}종목 / {len(df):,} 종목·일\n')

    # ── A. 파도 구조 ────────────────────────────────────────────────────────
    print('=' * 84)
    print('A. 연속 상승/하락 구간 길이 — 파도가 실제로 있는가')
    print('=' * 84)
    ups, downs = [], []
    for code, g in df.groupby('code'):
        sg = np.sign(g['ret'])
        sg = sg[sg != 0]
        for ln, first in zip(run_lengths(sg), []):
            pass
        s = sg.dropna()
        if len(s) == 0:
            continue
        grp = (s != s.shift()).cumsum()
        for _, run in s.groupby(grp):
            (ups if run.iloc[0] > 0 else downs).append(len(run))

    def dist(name, arr):
        a = np.array(arr)
        if len(a) == 0:
            return
        print(f'  {name}: 평균 {a.mean():.2f}일 / 중앙 {np.median(a):.0f}일 / '
              f'최대 {a.max()}일 / 3일이상 {np.mean(a >= 3) * 100:.1f}% / '
              f'5일이상 {np.mean(a >= 5) * 100:.1f}%')
    dist('연속 상승', ups)
    dist('연속 하락', downs)
    print('  ※ 동전던지기(무작위)라면 평균 2.00일, 3일이상 25%, 5일이상 6.25%가 기대값이다.')

    # ── B. 자기상관 ─────────────────────────────────────────────────────────
    print()
    print('=' * 84)
    print('B. 일간 수익률 자기상관 — 양수면 추세지속, 음수면 평균회귀')
    print('=' * 84)
    piv = df.pivot_table(index=df.index, columns='code', values='ret')
    for lag in (1, 2, 3, 5, 10):
        cors = piv.corrwith(piv.shift(lag))
        print(f'  lag {lag:>2}일: 평균 자기상관 {cors.mean():+.4f} '
              f'(양수 종목 비율 {np.mean(cors > 0) * 100:.1f}%)')

    # ── C. 전환 vs 추격 ─────────────────────────────────────────────────────
    print()
    print('=' * 84)
    print('C. 핵심 — 하락 후 반등(전환) vs 상승 지속(추격), 이후 수익률')
    print('=' * 84)
    d = df.sort_values(['code', df.index.name or None]) if False else df
    parts = []
    for code, g in df.groupby('code'):
        g = g.sort_index()
        c = g['close']
        prior5 = (c.shift(1) / c.shift(6) - 1) * 100     # 어제까지 직전 5일 수익률
        today = g['ret']
        fwd1 = (c.shift(-1) / c - 1) * 100
        fwd3 = (c.shift(-3) / c - 1) * 100
        fwd5 = (c.shift(-5) / c - 1) * 100
        parts.append(pd.DataFrame({
            'prior5': prior5, 'today': today, 'tv': g['tv'],
            'fwd1': fwd1, 'fwd3': fwd3, 'fwd5': fwd5,
        }))
    X = pd.concat(parts).dropna()
    X = X[X['tv'] >= MIN_TRADING_VALUE]
    print(f'거래대금 20억 이상 표본: {len(X):,}건\n')

    print(f'{"직전5일":<14}{"오늘":<14}{"건수":>9}{"익일%":>9}{"3일%":>9}{"5일%":>9}{"승률(3일)":>10}')
    print('-' * 84)
    prior_bands = [('급락 -10%↓', -1e9, -10), ('하락 -10~-3%', -10, -3),
                   ('보합 -3~+3%', -3, 3), ('상승 +3~+10%', 3, 10),
                   ('급등 +10%↑', 10, 1e9)]
    today_bands = [('오늘 +2~5%', 2, 5), ('오늘 +5%↑', 5, 1e9)]
    for pn, plo, phi in prior_bands:
        for tn, tlo, thi in today_bands:
            sub = X[(X['prior5'] > plo) & (X['prior5'] <= phi)
                    & (X['today'] > tlo) & (X['today'] <= thi)]
            if len(sub) < 200:
                continue
            print(f'{pn:<14}{tn:<14}{len(sub):>9,}{sub["fwd1"].mean():>9.3f}'
                  f'{sub["fwd3"].mean():>9.3f}{sub["fwd5"].mean():>9.3f}'
                  f'{(sub["fwd3"] > 0).mean() * 100:>9.1f}%')
        print('-' * 84)

    # 참고: 오늘 하락한 경우(반등 대기)도 같이 본다
    print()
    print('참고 — 오늘 하락한 종목의 이후 (반등을 기다리는 쪽)')
    print(f'{"직전5일":<14}{"오늘":<14}{"건수":>9}{"익일%":>9}{"3일%":>9}{"5일%":>9}{"승률(3일)":>10}')
    print('-' * 84)
    for pn, plo, phi in prior_bands:
        sub = X[(X['prior5'] > plo) & (X['prior5'] <= phi) & (X['today'] <= -2)]
        if len(sub) < 200:
            continue
        print(f'{pn:<14}{"오늘 -2%↓":<14}{len(sub):>9,}{sub["fwd1"].mean():>9.3f}'
              f'{sub["fwd3"].mean():>9.3f}{sub["fwd5"].mean():>9.3f}'
              f'{(sub["fwd3"] > 0).mean() * 100:>9.1f}%')

    print()
    print(f'전체 표본 평균: 익일 {X["fwd1"].mean():+.3f}% / 3일 {X["fwd3"].mean():+.3f}% / '
          f'5일 {X["fwd5"].mean():+.3f}%  ← 비교 기준선')


if __name__ == '__main__':
    main()
