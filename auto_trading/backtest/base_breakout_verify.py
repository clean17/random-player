# -*- coding: utf-8 -*-
"""베이스 돌파 전략 정직한 검증 (2026-08-19 작성).

base_breakout_study.py에서 시험구간 기대수익이 108개 조합 중 98개가 플러스로 나왔다.
다만 그 스크립트의 '최고 청산(손절-12%/20일, +2.973%)'은 **시험구간을 보고 고른 것**이라
과적합이다. 여기서는 규칙을 지킨다:

  1) 조합은 **훈련구간(2023-03~2024-12) 성적만으로** 고른다
  2) 청산은 **사전에 고정**한다 (손절 -8% / 10일 — study의 DEF_STOP/DEF_HOLD)
  3) 시험구간(2025-01~) 성적을 그대로 보고한다. 이게 결론이다
  4) 연도별로 쪼개 레짐 의존성을 본다
  5) 포트폴리오 CAGR을 훈련·시험 각각 낸다 — 훈련에서도 양수여야 신뢰할 수 있다

⚠️⚠️ **생존편향이 이 전략의 최대 약점이다.** pkl에는 현재 상장된 종목만 있다.
   '고점 대비 -30% 하락 후 다지기'는 정확히 상장폐지·관리종목이 몰리는 구간이므로,
   떨어진 뒤 사라진 종목이 표본에서 통째로 빠져 있다. rebound_signal.py도 같은 경고를
   달고 있다. 아래 수치는 **그만큼 낙관 쪽으로 치우쳐 있고, 그 편향의 크기를 이 데이터로는
   측정할 수 없다.** 실행 판단 전에 KRX 상장폐지 이력을 붙여 재검증해야 한다.

━━━ 결과 (2026-08-19, pkl 2,858종목, 조합 108개 중 훈련 성적으로 상위 3개 선정) ━━━

  조합 (낙폭,베이스,박스,수축,트리거)      구간  건수   건당%   중앙%   승률   2023   2024   2025   2026
  (-0.2, 20, 0.15, 0.9, 'ma20')      훈련   469  +0.567 -0.697 45.2% +2.444 -0.828
                                     시험   443  +1.208 -0.583 47.2%               +0.612 +3.011
  (-0.3, 20, 0.40, 0.9, 'ma20')      훈련   578  +0.486 -1.936 41.7% +2.338 -0.669
                                     시험   504  +1.198 -2.544 39.9%               -0.140 +4.933
  (-0.3, 20, 0.15, 0.9, 'ma20')      훈련   204  +0.450 -0.228 48.0% +1.854 -1.010
                                     시험   150  +1.195 -0.987 44.0%               +0.140 +5.794

  포트폴리오 CAGR (ratio 0.50 / 슬롯 5, 20회 부트)
                                     훈련 CAGR   시험 CAGR   훈련 음수경로  시험 MDD
  (-0.2, 20, 0.15, 0.9)               +2.3%      +7.1%        20%       -7.2
  (-0.3, 20, 0.40, 0.9)               +3.9%     +10.5%        15%      -10.1
  (-0.3, 20, 0.15, 0.9)               -0.1%      +5.4%        55%       -4.4

  ★ 건당 엣지는 현행보다 확실히 크다 — 시험 +1.20% vs 현행 전략 +0.07%(상한가 제외 기준).
    108개 조합 중 98개가 시험구간 플러스이고 훈련-시험 상관 +0.50이라 단일 조합의 운은 아니다.
    트리거는 상위 조합 전부 **MA20 회복**이다(박스 상단 돌파가 아니다).

  ⚠️ 1. **연도 편중이 심하다.** 2023 +1.9~+2.4 / 2024 **-0.7~-1.0** / 2025 -0.1~+0.6 /
       2026 **+3.0~+5.8**. 2023과 2026이 전부를 만들고 2024는 마이너스다. 이 프로젝트의
       판정 기준('모든 해에서 높아야 한다')을 통과하지 못한다.
  ⚠️ 2. **훈련 CAGR이 사실상 0이다**(+2.3 / +3.9 / -0.1, 음수경로 15~55%). 시험 +5~10%는
       2026년이 만든 값이다. '최대 CAGR'로 보기 어렵다.
  ⚠️ 3. **후보 공급이 구조적 상한이다.** 신호일당 2.0~3.0종목이고 신호가 나는 날 자체가
       179~362일(전체 ~840거래일)뿐이다. 슬롯 5를 채울 수 없어 ratio 0.50에서도 보유가
       52~59%에 묶인다. 계좌를 키워도 CAGR이 비례해 늘지 않는다.
  ⚠️ 4. **생존편향이 최대 위험이고 측정하지 못했다.** pkl에는 현재 상장 종목만 있다.
       '고점 대비 -20~-30% 하락 후 다지기'는 상장폐지·관리종목이 몰리는 구간이라,
       떨어진 뒤 사라진 종목이 표본에서 통째로 빠져 있다. 위 수치는 그만큼 낙관 쪽이고
       편향 크기를 이 데이터로는 알 수 없다. **실행 전 KRX 상장폐지 이력 결합이 필수다.**
  ⚠️ 5. 시가총액 700억 / 평균거래대금 40억 필터는 여기서도 미재현이다(pkl에 시총 없음).

  ※ base_breakout_study.py가 낸 '손절 -12%/20일 → +2.973%'는 **시험구간을 보고 고른 청산**이라
    과적합이다. 위 표는 청산을 사전 고정(-8%/10일)한 정직한 수치다.

사용법:
    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe auto_trading/backtest/base_breakout_verify.py
"""
import argparse
import itertools
import os
import sys

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from auto_trading.backtest.base_breakout_study import (                # noqa: E402
    load, collect, stat, SPLIT, COST, DEF_STOP, DEF_HOLD,
    DD_MINS, BASES, BOX_MAXS, VC_MAXS, TRIGGERS,
)
from auto_trading.backtest.cash_ratio_test import simulate             # noqa: E402


def cagr(total, years):
    return ((1 + total / 100) ** (1 / years) - 1) * 100 if total > -100 else -99.9


def port(C, capital, ratio, slots, iters, rng):
    if len(C) < 100:
        return None
    years = (C['D'].max() - C['D'].min()).days / 365.25
    if years < 0.5:
        return None
    s = simulate(C, capital, slots, slots, ratio, False, None)
    tot, ut = [], []
    for _ in range(iters):
        sub = C.groupby('D', group_keys=False).apply(
            lambda g: g.sample(max(1, int(len(g) * 0.8)),
                               random_state=int(rng.integers(1 << 31))))
        o = simulate(sub, capital, slots, slots, ratio, False, None)
        tot.append(o['total']); ut.append(o['util'])
    tot = np.array(tot)
    cg = np.array([cagr(t, years) for t in tot])
    return {'years': years, 'util': float(np.mean(ut)), 'cagr': cg.mean(),
            'lo': cg.min(), 'hi': cg.max(), 'neg': (tot < 0).mean() * 100,
            'mdd': s['mdd']}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--capital', type=int, default=1_990_000)
    ap.add_argument('--iters', type=int, default=20)
    ap.add_argument('--top', type=int, default=3)
    args = ap.parse_args()

    store = load(args.limit)
    print(f'유효 {len(store)}종목\n')

    combos = list(itertools.product(DD_MINS, BASES, BOX_MAXS, VC_MAXS, TRIGGERS))
    print(f'조합 {len(combos)}개 → 훈련 성적으로만 상위 {args.top}개 선정 '
          f'(청산 사전고정: 손절 {DEF_STOP:.0%} / {DEF_HOLD}일)\n')

    cand = []
    for combo in combos:
        X = collect(store, combo)
        if len(X) == 0:
            continue
        tr = X[X['D'] < SPLIT]
        s = stat(tr)
        if s is None or s['n'] < 150:
            continue
        cand.append((s['exp'], combo, X))
    cand.sort(key=lambda r: -r[0])
    print(f'훈련 표본 충족 {len(cand)}개 조합\n')

    rng = np.random.default_rng(20260819)
    years = [2023, 2024, 2025, 2026]

    hdr = (f'{"조합":<34}{"구간":<7}{"건수":>8}{"건당%":>9}{"중앙%":>9}{"승률":>8}'
           + ''.join(f'{y:>9}' for y in years))
    print('=' * len(hdr))
    print('훈련 상위 조합의 정직한 시험 성적 (청산 사전고정)')
    print('=' * len(hdr))
    print(hdr)
    print('-' * len(hdr))

    picks = []
    for exp_tr, combo, X in cand[:args.top]:
        picks.append((combo, X))
        for lab, sub in (('훈련', X[X['D'] < SPLIT]), ('시험', X[X['D'] >= SPLIT])):
            s = stat(sub)
            if s is None:
                continue
            by_y = sub.groupby(sub['D'].dt.year)['ret'].mean()
            print(f'{str(combo):<34}{lab:<7}{s["n"]:>8,}{s["exp"]:>9.3f}{s["med"]:>9.3f}'
                  f'{s["win"]:>7.1f}%'
                  + ''.join(f'{by_y.get(y, float("nan")) - COST:>9.3f}' if y in by_y.index
                            else f'{"-":>9}' for y in years))
        print('-' * len(hdr))
    print()

    print('=' * 92)
    print(f'포트폴리오 CAGR — 훈련·시험 각각 (ratio 0.50 / 슬롯 5, {args.iters}회 부트)')
    print('=' * 92)
    print(f'{"조합":<34}{"구간":<7}{"연수":>6}{"보유%":>7}{"CAGR":>9}{"CAGR범위":>18}'
          f'{"음수":>7}{"MDD%":>8}')
    print('-' * 92)
    for combo, X in picks:
        for lab, sub in (('훈련', X[X['D'] < SPLIT]), ('시험', X[X['D'] >= SPLIT])):
            C = sub[['D', 'entry', 'close_pos', 'ret', 'hold']].copy()
            r = port(C, args.capital, 0.50, 5, args.iters, rng)
            if r is None:
                print(f'{str(combo):<34}{lab:<7}   (표본/기간 부족)')
                continue
            rng_txt = '{:.1f} ~ {:.1f}%'.format(r['lo'], r['hi'])
            print(f'{str(combo):<34}{lab:<7}{r["years"]:>6.2f}{r["util"]:>7.1f}'
                  f'{r["cagr"]:>8.1f}%{rng_txt:>18}'
                  f'{r["neg"]:>6.0f}%{r["mdd"]:>8.1f}')
        print('-' * 92)
    print()
    print('※ 하루 후보 수가 적으면 슬롯을 다 못 채워 CAGR이 후보 공급에 묶인다.')
    for combo, X in picks:
        pd_ = X.groupby('D').size()
        print(f'  {combo}  전체 {len(X):,}건 / 신호일 {X["D"].nunique():,}일 / '
              f'신호일당 {pd_.mean():.1f}종목')


if __name__ == '__main__':
    main()
