# -*- coding: utf-8 -*-
"""매수 우선순위(정렬 기준) 검증 (2026-08-14 작성).

배경: signal_days=1로 바꾸면서 기존 정렬 키(총상승률)가 전 후보 0.0으로 동률이 돼
      무의미해졌다. 대체 기준 후보 3가지를 단독/합성으로 비교한다.
  1. 종가위치 높은순   (close_pos desc) — 윗꼬리 아닌 것
  2. 당일 등락률 낮은순 (chg asc)        — 과열 아닌 것
  3. 거래대금비 낮은순  (tvr asc)         — 거래량 급증 아닌 것

핵심 질문 두 개
  a) 후보가 슬롯(20)보다 많은 날이 얼마나 되나? 적으면 정렬은 애초에 별 의미가 없다.
  b) 합성 순위가 단일 기준보다 나은가?

정렬은 '그날 후보 중 상위 N개만 매수'로 시뮬레이션한다.
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

from auto_trading.backtest.first_signal_filter import build, SPLIT  # noqa: E402

CLOSE_POS_MIN = 0.6
SLOTS = 20


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--slots', type=int, default=SLOTS)
    args = ap.parse_args()

    X = build()
    X = X[X['close_pos'] >= CLOSE_POS_MIN].dropna(subset=['tvr', 'chg', 'ret']).copy()
    print(f'첫 신호일 + 종가위치>={CLOSE_POS_MIN} 표본 {len(X):,}건')

    # a) 하루 후보 수 분포
    per_day = X.groupby('D').size()
    print(f'일평균 후보 {per_day.mean():.1f}종목 / 중앙 {per_day.median():.0f} / 최대 {per_day.max()}')
    over = (per_day > args.slots).mean() * 100
    print(f'후보가 슬롯({args.slots})을 넘는 날: {over:.1f}%  '
          f'→ 이 비율이 낮으면 정렬 기준의 영향은 제한적이다\n')

    # 일자별 순위 (0=가장 좋음)
    g = X.groupby('D')
    X['r_pos'] = g['close_pos'].rank(ascending=False, pct=True)   # 높을수록 좋음
    X['r_chg'] = g['chg'].rank(ascending=True, pct=True)          # 낮을수록 좋음
    X['r_tvr'] = g['tvr'].rank(ascending=True, pct=True)          # 낮을수록 좋음
    X['r_mix'] = (X['r_pos'] + X['r_chg'] + X['r_tvr']) / 3

    def topn(key, n):
        return X[X.groupby('D')[key].rank(method='first') <= n]

    print('=' * 92)
    print(f'정렬 기준별 — 그날 상위 {args.slots}종목만 매수했을 때 (3거래일 보유)')
    print('=' * 92)
    print(f'{"정렬 기준":<26}{"건수":>8}{"평균%":>9}{"중앙%":>9}{"승률":>8}'
          f'{"MDD%":>8}{"전반기%":>9}{"후반기%":>9}')
    print('-' * 92)

    rows = [
        ('전체(정렬 무관)', X),
        ('1. 종가위치 높은순', topn('r_pos', args.slots)),
        ('2. 당일등락률 낮은순', topn('r_chg', args.slots)),
        ('3. 거래대금비 낮은순', topn('r_tvr', args.slots)),
        ('합성(1+2+3 평균순위)', topn('r_mix', args.slots)),
    ]
    for label, sub in rows:
        h1 = sub[sub['D'] <= SPLIT]['ret']
        h2 = sub[sub['D'] > SPLIT]['ret']
        print(f'{label:<26}{len(sub):>8,}{sub["ret"].mean():>9.3f}{sub["ret"].median():>9.3f}'
              f'{(sub["ret"] > 0).mean() * 100:>7.1f}%{sub["mdd"].mean():>8.2f}'
              f'{h1.mean():>9.3f}{h2.mean():>9.3f}')

    # 슬롯을 줄이면(집중 매수) 정렬 효과가 더 드러난다
    print()
    print('=' * 92)
    print('슬롯을 줄였을 때 (정렬이 실제로 변별력이 있는지)')
    print('=' * 92)
    print(f'{"정렬 기준":<26}' + ''.join(f'{f"상위{n}":>12}' for n in (3, 5, 10, 20)))
    print('-' * 92)
    for label, key in [('1. 종가위치', 'r_pos'), ('2. 등락률낮은순', 'r_chg'),
                       ('3. 거래대금비낮은순', 'r_tvr'), ('합성', 'r_mix')]:
        cells = []
        for n in (3, 5, 10, 20):
            s = topn(key, n)
            cells.append(f'{s["ret"].mean():>12.3f}')
        print(f'{label:<26}' + ''.join(cells))
    print()
    print(f'{"(비교) 전체 평균":<26}{X["ret"].mean():>12.3f}')


if __name__ == '__main__':
    main()
