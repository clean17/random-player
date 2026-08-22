# -*- coding: utf-8 -*-
"""'떨어지는 걸 사기' vs '반등 확인하고 사기' — 위험까지 포함해 비교 (2026-08-14 작성).

계기: wave_analysis.py에서 '급락 + 오늘도 하락'의 5일 평균이 +1.215%로 가장 높게 나왔는데,
      "그건 5일 내내 더 떨어질 수도 있는 것 아니냐, 반등을 확인하고 사는 게 확실하지 않냐"는
      지적. 평균만으로는 답이 안 되므로 하방 위험과 분포를 같이 잰다.

측정 항목 (진입 후 5거래일)
  평균/중앙값, 승률
  최대낙폭(MDD) : 진입가 대비 5일 내 최저가까지의 낙폭 — '얼마나 더 떨어지는가'
  P(-5%↓)      : 5일 내 -5% 아래로 내려간 적이 있는 비율
  하위10%      : 수익률 하위 10분위 (최악 구간이 얼마나 나쁜가)

반등 정의를 여러 가지로 나눠 '무엇이 전환을 특정해주는가'를 찾는다.
⚠️ 생존 편향: pkl에 상장폐지 종목이 없다. 급락 구간에서 특히 낙관 쪽으로 치우친다.
"""
import argparse
import os
import sys
import glob

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

PKL_DIR = r'C:\my-project\AutoSales.py\data\pickle'
MIN_TV = 2_000_000_000
FWD = 5


def build(start):
    parts = []
    for path in sorted(glob.glob(os.path.join(PKL_DIR, '*.pkl'))):
        try:
            df = pd.read_pickle(path)
        except Exception:
            continue
        need = {'종가', '거래량', '저가', '고가'}
        if df is None or len(df) < 60 or not need.issubset(df.columns):
            continue
        if not isinstance(df.index, pd.DatetimeIndex):
            continue
        d = df[df.index >= start]
        if len(d) < 60:
            continue
        c = d['종가'].astype(float)
        lo = d['저가'].astype(float)
        vol = d['거래량'].astype(float)

        ret = c.pct_change() * 100
        # 진입 후 FWD일 동안의 최저가 / 종가
        fwd_min = lo.shift(-FWD).rolling(FWD, min_periods=1).min()   # 잘못된 정렬 방지용으로 아래서 재계산
        fwd_low = pd.concat([lo.shift(-k) for k in range(1, FWD + 1)], axis=1).min(axis=1)
        fwd_close = c.shift(-FWD)

        # 직전 하락 지속일수 (오늘 제외, 어제까지 연속 음수일)
        neg = (ret < 0).astype(int)
        streak = neg.copy()
        run = 0
        vals = []
        for v in neg.shift(1).fillna(0).values:
            run = run + 1 if v == 1 else 0
            vals.append(run)
        down_streak = pd.Series(vals, index=c.index)

        parts.append(pd.DataFrame({
            'prior5': (c.shift(1) / c.shift(6) - 1) * 100,
            'today': ret,
            'down_streak': down_streak,
            'vol_ratio': vol / vol.shift(1).rolling(5).mean(),
            'tv': c * vol,
            'fwd_ret': (fwd_close / c - 1) * 100,
            'fwd_mdd': (fwd_low / c - 1) * 100,
        }))
    X = pd.concat(parts).dropna()
    return X[X['tv'] >= MIN_TV]


def row(label, sub, base=None):
    if len(sub) < 300:
        print(f'{label:<34}{len(sub):>8,}  (표본부족)')
        return
    r = sub['fwd_ret']
    print(f'{label:<34}{len(sub):>8,}{r.mean():>9.3f}{r.median():>9.3f}'
          f'{(r > 0).mean() * 100:>8.1f}%{sub["fwd_mdd"].mean():>9.2f}'
          f'{(sub["fwd_mdd"] <= -5).mean() * 100:>9.1f}%{r.quantile(0.10):>9.2f}'
          f'{r.std():>8.2f}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', default='2023-01-01')
    args = ap.parse_args()

    print(f'pkl 로드 중... (>= {args.start})')
    X = build(pd.Timestamp(args.start))
    print(f'표본 {len(X):,}건 (거래대금 20억 이상)\n')

    hdr = (f'{"조건":<34}{"건수":>8}{"평균%":>9}{"중앙%":>9}{"승률":>8}'
           f'{"평균MDD%":>9}{"P(-5%↓)":>9}{"하위10%":>9}{"표준편차":>8}')
    print('=' * 104)
    print(f'진입 후 {FWD}거래일 성과 — MDD/P(-5%)가 "더 떨어질 위험"이다')
    print('=' * 104)
    print(hdr)
    print('-' * 104)
    row('전체 (기준선)', X)
    print('-' * 104)

    crash = X['prior5'] <= -10
    print('■ 급락(직전5일 -10%↓) 이후')
    row('  오늘도 하락 (-2%↓) = 떨어지는 걸 매수', X[crash & (X['today'] <= -2)])
    row('  오늘 보합 (-2~+2%)', X[crash & (X['today'] > -2) & (X['today'] < 2)])
    row('  오늘 반등 +2~5%', X[crash & (X['today'] >= 2) & (X['today'] < 5)])
    row('  오늘 반등 +5%↑', X[crash & (X['today'] >= 5)])
    print('-' * 104)

    print('■ 반등 정교화 — 하락 지속일수 + 반등 강도 조합 (직전5일 -10%↓)')
    for ds in (2, 3, 4):
        for lo, hi, nm in ((2, 5, '+2~5%'), (5, 100, '+5%↑')):
            row(f'  {ds}일연속하락 후 반등 {nm}',
                X[crash & (X['down_streak'] >= ds) & (X['today'] >= lo) & (X['today'] < hi)])
    print('-' * 104)

    print('■ 거래량 동반 여부 (직전5일 -10%↓ & 오늘 +2%↑)')
    reb = crash & (X['today'] >= 2)
    row('  거래량 5일평균 대비 2배↑', X[reb & (X['vol_ratio'] >= 2)])
    row('  거래량 1~2배', X[reb & (X['vol_ratio'] >= 1) & (X['vol_ratio'] < 2)])
    row('  거래량 1배 미만', X[reb & (X['vol_ratio'] < 1)])
    print('-' * 104)

    print('■ 비교군 — 현재 fire 신호에 가까운 구조 (급등 추격)')
    row('  직전5일 +10%↑ & 오늘 +2~5%', X[(X['prior5'] >= 10) & (X['today'] >= 2) & (X['today'] < 5)])
    row('  직전5일 +10%↑ & 오늘 +5%↑', X[(X['prior5'] >= 10) & (X['today'] >= 5)])


if __name__ == '__main__':
    main()
