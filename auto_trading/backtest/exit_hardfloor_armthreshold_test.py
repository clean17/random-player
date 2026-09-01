# -*- coding: utf-8 -*-
"""v8 청산(ATR샹들리에+트레일링-5%+익절+20%, 현재 라이브 설정) 대비 3가지 변형 비교
(2026-09-01 작성, 사용자 요청: 189330/011300처럼 얕은 고점 후 트레일링이 손실로 발동하거나
ATR이 넓어 손절이 사실상 안 걸리는 종목 대응).

━━━ 비교 대상 4가지 (전부 max_hold=10영업일 — kiwoom_v8_exit.py 실제 라이브 값) ━━━
  현재            : ATR(14)x3.0 샹들리에 + 트레일링-5%(무조건 무장) + 익절+20% (라이브 그대로)
  A. ATR넓은종목만-15%하한 : 진입 시점 3*ATR/진입가 > 15%인 종목만 추가로 -15% 하드 손절을 같이 건다
                      (좁은 ATR 종목은 현재와 완전히 동일 — 샹들리에가 이미 15%보다 타이트하므로)
  B. 일괄-15%하한   : 모든 종목에 -15% 하드 손절을 추가(먼저 도달하는 쪽이 발동), 샹들리에/트레일링은 유지
  C. 최소고점임계값(+5%) : peak >= entry*1.05 이상 찍어야 트레일링(-5%)이 무장 (그 전엔 샹들리에만 방어)

건별 지표(exit_chandelier_test.py와 동일 방식)와, 포트폴리오 CAGR(cagr_estimate.py의
cash_ratio_test.simulate 재사용, RATIO=0.65/SLOTS=5/DIVISOR=5/pool=7 라이브 근사치)을 같이 낸다.

⚠️ CAGR 절대값은 cagr_estimate.py에 이미 기록된 이유(상한가 종목 종가매수 가정)로 신뢰할 수
없다 — 단, 4개 변형이 완전히 동일한 진입 후보(S1)를 공유하므로 상한가 오염은 네 변형에
동일하게 들어가 **상대 비교(현재 대비 어느 변형이 낫다/못하다)는 유효**하다. 절대 CAGR을
실계좌 기대치로 읽지 말 것.

사용법:
    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe auto_trading/backtest/exit_hardfloor_armthreshold_test.py
    ... --limit 400   (빠른 확인용, 종목 수 제한)
"""
import argparse
import os
import sys
from typing import Optional

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from auto_trading.backtest import strategy_matrix as SM                    # noqa: E402
from auto_trading.backtest.entry_threshold_test import CLOSE_POS_MIN       # noqa: E402
from auto_trading.backtest.exit_chandelier_test import atr_wilder          # noqa: E402
from auto_trading.backtest.cash_ratio_test import simulate as port_sim, COST  # noqa: E402

ROUND_TRIP = 0.21
ATR_N = 14
ATR_MULT = 3.0
TRAIL_DROP = 0.05
TAKE_PROFIT = 0.20
MAX_HOLD = 10           # kiwoom_v8_exit.py MAX_HOLD_DAYS (실제 라이브 값)
RATIO, SLOTS, DIVISOR, POOL = 0.65, 5, 5, 7   # cagr_estimate.py와 동일(실측 후보 7종목 근사)


def sim_new(d, i, atr, max_hold=MAX_HOLD, trail_arm=0.0,
            hard_stop=None, hard_stop_if_wide=None):
    """exit_chandelier_test.sim_new()에 hard_stop_if_wide만 추가한 버전.

    hard_stop_if_wide: 진입 시점 3*ATR/entry 가 이 값의 절대값보다 크면(=샹들리에가
    이 하한보다 넓으면) 그 종목에 한해 hard_stop과 동일한 하드 손절을 같이 건다.
    좁은 ATR 종목은 건드리지 않는다(샹들리에가 이미 더 타이트해서 하한이 무의미함).
    """
    op, hi, lo, cl = d['op'], d['hi'], d['lo'], d['cl']
    entry = cl[i]
    if entry <= 0:
        return None
    last = min(i + max_hold, len(cl) - 1)
    if last <= i:
        return None

    a0 = atr[i]
    effective_hard_stop = hard_stop
    if hard_stop_if_wide is not None and np.isfinite(a0):
        is_wide = (ATR_MULT * a0 / entry) > abs(hard_stop_if_wide)
        effective_hard_stop = hard_stop_if_wide if is_wide else None

    remaining = 1.0
    realized = []
    reasons = []
    peak = entry
    armed_peak = None
    took_profit = False
    j = i

    for j in range(i + 1, last + 1):
        o, h, l = op[j], hi[j], lo[j]
        a = atr[j]

        if not took_profit and h >= entry * (1 + TAKE_PROFIT):
            sell = remaining * 0.5
            realized.append((sell, TAKE_PROFIT * 100))
            remaining -= sell
            took_profit = True
            reasons.append('take20')

        peak = max(peak, h)

        if remaining > 1e-9 and peak >= entry * (1 + trail_arm):
            level = peak * (1 - TRAIL_DROP)
            rearmed = armed_peak is None or peak > armed_peak
            if rearmed and l <= level:
                fill = level if o > level else o
                sell = remaining * 0.5
                realized.append((sell, (fill / entry - 1) * 100))
                remaining -= sell
                armed_peak = peak
                reasons.append('trail5')

        if effective_hard_stop is not None and remaining > 1e-9:
            hs = entry * (1 + effective_hard_stop)
            if l <= hs:
                fill = hs if o > hs else o
                realized.append((remaining, (fill / entry - 1) * 100))
                remaining = 0.0
                reasons.append('hardfloor')
                break

        if remaining > 1e-9 and np.isfinite(a):
            ch = peak - ATR_MULT * a
            if l <= ch:
                fill = ch if o > ch else o
                realized.append((remaining, (fill / entry - 1) * 100))
                remaining = 0.0
                reasons.append('chandelier')
                break

        if remaining <= 1e-9:
            break

    truncated = False
    if remaining > 1e-9:
        truncated = (i + max_hold) > (len(cl) - 1)
        realized.append((remaining, (cl[j] / entry - 1) * 100))
        reasons.append('trunc' if truncated else 'time')

    ret = sum(w * r for w, r in realized)
    return ret, j - i, '|'.join(reasons), truncated


VARIANTS = [
    ('현재(라이브)',              lambda d, i, a: sim_new(d, i, a)),
    ('A.ATR넓은종목만-15%하한',   lambda d, i, a: sim_new(d, i, a, hard_stop_if_wide=-0.15)),
    ('B.일괄-15%하한',           lambda d, i, a: sim_new(d, i, a, hard_stop=-0.15)),
    ('C.최소고점임계값(+5%)',     lambda d, i, a: sim_new(d, i, a, trail_arm=0.05)),
]


def build(limit: Optional[int] = None):
    store, mkt, market_ret5 = SM.load_store(limit)
    print('청산 시뮬레이션...', flush=True)
    rows = []
    for n, (code, d) in enumerate(store.items(), 1):
        if n % 500 == 0:
            print(f'  ... {n}/{len(store)}', flush=True)
        d = dict(d)
        d['hi'] = d['df']['고가'].astype(float).to_numpy()
        atr = atr_wilder(d['hi'], d['lo'], d['cl'])

        base, chg, cpos = d['base'], d['chg'], d['cpos']
        sig = base & (chg >= 3.0) & (cpos >= CLOSE_POS_MIN)
        if not sig.any():
            continue
        sd = SM.signal_days(sig)
        for i in np.flatnonzero(sig & (sd == 1)):
            rec = {'D': d['idx'][i], 'entry': d['cl'][i], 'close_pos': cpos[i]}
            ok = False
            for vname, fn in VARIANTS:
                r = fn(d, i, atr)
                if r is None or r[3]:
                    rec[vname] = np.nan
                    rec[vname + '_h'] = np.nan
                else:
                    rec[vname] = r[0]
                    rec[vname + '_h'] = r[1]
                    ok = True
            if ok:
                rows.append(rec)
    return pd.DataFrame(rows)


def cagr(total_pct, years):
    return ((1 + total_pct / 100.0) ** (1.0 / years) - 1) * 100


def report_per_trade(X):
    print('=' * 78)
    print('건별 지표 (S1 진입: signal_days=1, 등락률>=3%, 종가위치>=0.6)')
    print('=' * 78)
    hdr = f'{"변형":<26}{"건수":>8}{"기대수익%":>11}{"중앙%":>9}{"승률":>8}{"보유일":>8}'
    print(hdr)
    print('-' * len(hdr))
    for vname, _ in VARIANTS:
        s = X[X[vname].notna()]
        exp = s[vname].mean() - ROUND_TRIP
        med = s[vname].median()
        win = (s[vname] > 0).mean() * 100
        hold = s[vname + '_h'].mean()
        print(f'{vname:<26}{len(s):>8,}{exp:>11.3f}{med:>9.3f}{win:>7.1f}%{hold:>8.2f}')
    print()


def report_cagr(X, capital, iters, seed=20260901):
    d0, d1 = X['D'].min(), X['D'].max()
    years = (d1 - d0).days / 365.25
    print('=' * 90)
    print(f'포트폴리오 CAGR (RATIO={RATIO}/SLOTS={SLOTS}/DIVISOR={DIVISOR}/pool={POOL} 실측 근사, '
          f'{d0.date()}~{d1.date()}={years:.2f}년, {iters}회 부트스트랩)')
    print('⚠️ 절대 CAGR은 상한가 매수 가정으로 과대추정됨(cagr_estimate.py 참고) — 4개 변형 간 '
          '"현재" 대비 상대 순위/차이만 신뢰할 것')
    print('=' * 90)
    hdr = f'{"변형":<26}{"단일경로총수익%":>16}{"CAGR":>9}{"MDD%":>8}{"부트CAGR평균":>13}{"CAGR범위":>18}'
    print(hdr)
    print('-' * len(hdr))
    rng = np.random.default_rng(seed)
    baseline_cagr = None
    for vname, _ in VARIANTS:
        cand = X[X[vname].notna()][['D', 'entry', 'close_pos']].copy()
        cand['ret'] = X.loc[cand.index, vname]
        cand['hold'] = X.loc[cand.index, vname + '_h']
        s = port_sim(cand, capital, SLOTS, DIVISOR, RATIO, False, POOL)
        tot = []
        for _ in range(iters):
            sub = cand.groupby('D', group_keys=False).apply(
                lambda g: g.sample(max(1, int(len(g) * 0.8)),
                                   random_state=int(rng.integers(1 << 31))))
            tot.append(port_sim(sub, capital, SLOTS, DIVISOR, RATIO, False, POOL)['total'])
        tot = np.array(tot)
        cg = np.array([cagr(t, years) for t in tot])
        single_cagr = cagr(s['total'], years)
        if baseline_cagr is None:
            baseline_cagr = single_cagr
        diff = single_cagr - baseline_cagr
        diff_txt = '' if vname == VARIANTS[0][0] else f' ({diff:+.1f}%p vs 현재)'
        print(f'{vname:<26}{s["total"]:>15.1f}%{single_cagr:>8.1f}%{s["mdd"]:>8.1f}'
              f'{cg.mean():>12.1f}%{f"{cg.min():.1f}~{cg.max():.1f}%":>18}{diff_txt}')
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--capital', type=int, default=1_990_000)
    ap.add_argument('--iters', type=int, default=25)
    args = ap.parse_args()

    X = build(limit=args.limit)
    print(f'\n총 {len(X):,}건\n')
    report_per_trade(X)
    report_cagr(X, args.capital, args.iters)

    # 하드플로어 발동 빈도 확인 (A/B가 실제로 얼마나 자주 손절 사유를 바꾸는지)
    for vname in ('A.ATR넓은종목만-15%하한', 'B.일괄-15%하한'):
        s = X[X[vname].notna()]
        print(f'{vname}: 표본 {len(s):,}건 (참고: 발동 사유별 집계는 필요시 _r 컬럼 추가해 확인)')


if __name__ == '__main__':
    main()
