# -*- coding: utf-8 -*-
"""데드캣바운스 필터 검증 — '반등이 지속되는지 확인하고 사면 더 나은가' (2026-08-14 작성).

계기: rebound_signal.py에서 급락 후 반등 1일차 매수가 평균 +0.417%지만 중앙값 -0.837%,
      P(-5%↓) 65.9%로 위험만 컸다. "데드캣바운스일 수 있으니 그걸 극복한 종목은 더 가지
      않겠냐"는 가설을 검증한다.

확인(confirmation) 조건을 여러 가지로 두고, 확인이 끝난 날 종가에 진입한다고 가정한다.
  1일차       : 급락 후 첫 상승일 (기준 — 확인 없음)
  2일연속상승 : 첫 상승 다음 날도 상승
  3일연속상승
  MA5 회복    : 반등일 종가가 MA5 위
  MA20 회복   : 반등일 종가가 MA20 위
  낙폭 절반회복: 반등일 종가가 (직전 고점+저점)/2 위
  전고점 돌파 : 반등일 종가가 직전 10일 고가 위

측정: 진입 후 5거래일 평균/중앙/승률 + 하방위험(MDD, P(-5%↓))
⚠️ 생존 편향: pkl에 상장폐지 종목이 없어 급락 구간이 낙관 쪽으로 치우친다.
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
CRASH = -10.0     # 직전 5일 수익률이 이 값 이하면 '급락'


def build(start):
    parts = []
    for path in sorted(glob.glob(os.path.join(PKL_DIR, '*.pkl'))):
        try:
            df = pd.read_pickle(path)
        except Exception:
            continue
        need = {'종가', '거래량', '저가', '고가'}
        if df is None or len(df) < 80 or not need.issubset(df.columns):
            continue
        if not isinstance(df.index, pd.DatetimeIndex):
            continue
        d = df[df.index >= start]
        if len(d) < 80:
            continue
        c = d['종가'].astype(float)
        hi = d['고가'].astype(float)
        lo = d['저가'].astype(float)
        vol = d['거래량'].astype(float)
        ret = c.pct_change() * 100

        up = ret > 0
        fwd_low = pd.concat([lo.shift(-k) for k in range(1, FWD + 1)], axis=1).min(axis=1)

        # '오늘이 반등 n일차'인지 — 오늘 포함 연속 상승일수
        up_run = []
        run = 0
        for v in up.fillna(False).values:
            run = run + 1 if v else 0
            up_run.append(run)
        up_run = pd.Series(up_run, index=c.index)

        # 반등 시작 직전(= 연속 상승 시작 전날)의 직전5일 수익률로 '급락 여부'를 판정해야
        # 확인 일수를 늘려도 같은 사건을 비교할 수 있다.
        prior5 = (c.shift(1) / c.shift(6) - 1) * 100
        prior5_at_start = prior5.copy()
        for n in range(1, 6):
            prior5_at_start = prior5_at_start.where(up_run != n, prior5.shift(n - 1))

        parts.append(pd.DataFrame({
            'up_run': up_run,
            'crash_before': prior5_at_start,
            'today': ret,
            'ma5_ok': c > c.rolling(5).mean(),
            'ma20_ok': c > c.rolling(20).mean(),
            'half_recover': c > (hi.rolling(10).max() + lo.rolling(10).min()) / 2,
            'break_high10': c > hi.rolling(10).max().shift(1),
            'vol_ratio': vol / vol.shift(1).rolling(5).mean(),
            'tv': c * vol,
            'fwd_ret': (c.shift(-FWD) / c - 1) * 100,
            'fwd_mdd': (fwd_low / c - 1) * 100,
        }))
    X = pd.concat(parts).dropna()
    return X[X['tv'] >= MIN_TV]


def row(label, sub):
    if len(sub) < 300:
        print(f'{label:<32}{len(sub):>8,}   (표본부족)')
        return
    r = sub['fwd_ret']
    print(f'{label:<32}{len(sub):>8,}{r.mean():>9.3f}{r.median():>9.3f}'
          f'{(r > 0).mean() * 100:>8.1f}%{sub["fwd_mdd"].mean():>9.2f}'
          f'{(sub["fwd_mdd"] <= -5).mean() * 100:>9.1f}%{r.std():>8.2f}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', default='2023-01-01')
    args = ap.parse_args()

    print(f'pkl 로드 중... (>= {args.start})')
    X = build(pd.Timestamp(args.start))
    print(f'표본 {len(X):,}건 (거래대금 20억 이상)\n')

    hdr = (f'{"조건":<32}{"건수":>8}{"평균%":>9}{"중앙%":>9}{"승률":>8}'
           f'{"평균MDD%":>9}{"P(-5%↓)":>9}{"표준편차":>8}')
    print('=' * 96)
    print(f'급락(반등 시작 전 5일 {CRASH}%↓) 이후, 확인 조건별 진입 성과 (진입 후 {FWD}일)')
    print('=' * 96)
    print(hdr)
    print('-' * 96)
    row('전체 (기준선)', X)
    print('-' * 96)

    crash = X['crash_before'] <= CRASH
    print('■ 확인 일수')
    row('  반등 1일차 (확인 없음)', X[crash & (X['up_run'] == 1)])
    row('  반등 2일연속', X[crash & (X['up_run'] == 2)])
    row('  반등 3일연속', X[crash & (X['up_run'] == 3)])
    row('  반등 4일연속', X[crash & (X['up_run'] == 4)])
    print('-' * 96)

    print('■ 가격 회복 확인 (반등 중 = up_run>=1)')
    reb = crash & (X['up_run'] >= 1)
    row('  MA5 회복', X[reb & X['ma5_ok']])
    row('  MA20 회복', X[reb & X['ma20_ok']])
    row('  낙폭 절반 회복', X[reb & X['half_recover']])
    row('  직전10일 고가 돌파', X[reb & X['break_high10']])
    print('-' * 96)

    print('■ 조합 (2일연속 + 가격확인)')
    two = crash & (X['up_run'] >= 2)
    row('  2일연속 + MA5 회복', X[two & X['ma5_ok']])
    row('  2일연속 + MA20 회복', X[two & X['ma20_ok']])
    row('  2일연속 + 낙폭절반 회복', X[two & X['half_recover']])
    row('  2일연속 + 고가돌파', X[two & X['break_high10']])
    print('-' * 96)

    print('■ 거래량 조건 추가 (2일연속 + MA5 회복)')
    base = two & X['ma5_ok']
    row('  거래량 2배↑', X[base & (X['vol_ratio'] >= 2)])
    row('  거래량 1~2배', X[base & (X['vol_ratio'] >= 1) & (X['vol_ratio'] < 2)])
    row('  거래량 1배 미만', X[base & (X['vol_ratio'] < 1)])


if __name__ == '__main__':
    main()
