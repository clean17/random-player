# -*- coding: utf-8 -*-
"""신규 청산안(샹들리에 ATR + 트레일링 -5% + 익절 +20%) vs 현행 검증 (2026-08-19 작성).

━━━ 요청받은 신규 청산안 ━━━
  ① ATR(14) x 3.0 샹들리에 손절 : 진입 후 최고가 - 3.0*ATR 이탈 → 잔여 전량
  ② 트레일링 -5%               : 최고가 대비 -5% 터치 → 잔여의 절반, 고점 갱신 시 재무장
  ③ 익절 +20%                  : 진입가 +20% 도달 → 잔여의 절반 (1회만)

━━━ 명세에 없어서 따로 분해한 것 ━━━
  - **시간상한이 없다.** 백테스트는 종료 조건이 필요하므로 40거래일에서 끊고 그 비율을 보고한다.
    별도로 '신규 + 5일 상한' 변형도 같이 낸다(현행과 보유기간을 맞춘 비교).
  - **-6% 하드 손절이 없다.** ①이 그 역할을 대신하는데, ATR이 가격의 ~4%면 3*ATR = 12%로
    현행 -6%보다 훨씬 느슨하다. 그래서 '신규 + 손절 -6%' 변형도 같이 낸다.
  - 기여도 분해: ①만 / ①+② / ①+②+③ 를 누적으로 쌓아 어느 항목이 실제로 값을 만드는지 본다.

━━━ 구현 규약 ━━━
  ATR(14)   : True Range = max(고-저, |고-전일종가|, |저-전일종가|), Wilder 평활(alpha=1/14).
              매일 갱신된 당일 ATR을 쓴다(표준 Chandelier Exit).
  최고가     : 진입가(신호일 종가)에서 시작해 이후 각 날의 고가로 갱신한다.
              신호일 고가는 넣지 않는다 — 신호일은 급등일이라 그 고가를 넣으면 진입 직후
              샹들리에선이 비현실적으로 높아진다.
  하루 처리 순서 : 익절(고가) → 최고가 갱신 → 트레일링(저가) → 샹들리에(저가)
              fire_backtest_regen.simulate_exit와 같은 관례. 일봉으로는 일중 순서를 알 수 없어
              '올랐다가 밀린 날'을 라이브와 같게 재현하는 대신, 저점 먼저 찍고 반등한 날은
              실제보다 불리하게 계산된다.
  체결가     : 트리거선 가격. 갭으로 트리거선을 건너뛴 날은 시가.
  비용       : 왕복 0.21% 일괄 차감. 분할 매도는 비용을 늘리지 않는다(수수료·거래세가 금액 비례).

진입은 현행 라이브와 동일한 S1(signal_days=1, 등락률>=3%, 종가위치>=0.6)을 쓰고,
S2(상대강도 밴드)로도 같이 돌려 결론이 진입 집단에 의존하는지 확인한다.

━━━ 결과 (2026-08-19, pkl 2,858종목 / 2023-03~2026-08, S1 31,405건 · 왕복비용 0.21% 차감) ━━━

  청산 규칙                     건수    기대수익%   중앙%    승률  보유일   2023    2024    2025    2026
  현행 B: 손절-6%+5일        31,405   +0.186   -1.900  39.5%  3.96  +0.061 +0.022 +0.397 +0.268
  현행 A: 트레일링15일        31,401   -0.859   -4.185  40.1%  5.83  -0.934 -1.267 -0.464 -0.760
  신규 ①+②+③ +5일상한       31,409   -1.002   -1.366  38.2%  4.67  -1.039 -1.210 -0.745 -1.039
  신규 (②는 +7%) +5일상한    31,409   -1.011   -0.576  46.0%  4.67  -1.085 -1.279 -0.603 -1.145
  신규 ①+②+③ +손절-6%      31,176   -1.105   -2.775  31.7%  9.43  -1.162 -1.427 -0.722 -1.141
  신규 ②+③만(샹들리에 없음)   30,128   -1.370   -1.025  43.0% 40.00  -1.477 -2.047 -0.218 -2.145
  신규 ①+②+③ (요청안)       30,929   -1.517   -1.945  36.1% 14.33  -1.495 -1.904 -0.931 -1.900
  신규 ①+②                 30,929   -1.901   -2.118  33.7% 14.33  -1.836 -2.290 -1.306 -2.356
  신규 ①+②+③ (②는 +7%부터)  30,929   -1.991   -1.292  45.6% 14.33  -1.902 -2.603 -0.939 -2.887
  신규 ①만(샹들리에)          30,929   -2.060   -4.736  31.7% 14.33  -2.181 -2.948 +0.010 -3.916

  S2 진입(상대강도 밴드)으로 돌려도 순위가 같다 — 현행 B +0.230, 요청안 -1.678.
  **현행 B만 양수이고, 신규안 전 변형이 4개 연도 전부 마이너스다.** 요청안과 현행의 차이 -1.703%p.

  ★ 1. 샹들리에(①)가 사실상 발동하지 않는다 — 첫 청산 사유의 **0.1%**(20건/30,929건).
       3*ATR이 가격의 ~12%라 현행 손절 -6%의 두 배로 느슨하고, 그 사이 하방이 무방비다.
       ①만 쓰면 -2.060으로 전 변형 중 최악이다.

  ★ 2. 실제로 일을 하는 건 ②이고(첫 사유의 95.8%) 그것도 의도와 다르게 작동한다.
       ②에 활성 조건이 없어 최고가=진입가 상태에서 **-5%에 즉시 발동**한다. 즉 '트레일링'이
       아니라 '절반만 잘라내는 -5% 손절'로 동작한다.
       ③ take20은 4.0%, 시간종료 0.1%.

  ★ 3. **완전 청산 경로가 없다.** ②는 잔여의 절반(재무장 필요), ③은 1회 절반, 전량 청산은 ①뿐인데
       그게 0.1%만 발동한다. 그래서 ①을 빼면(②+③만) 평균 보유가 상한 40일에 그대로 붙는다.
       시간상한 없이 이 조합을 쓰면 포지션이 기하급수적으로 줄기만 하고 닫히지 않는다.

  ★ 4. 평균 보유 14.33일 vs 현행 3.96일. 이 신호의 수익은 1~3일에 몰리고 10일 -0.918% /
       20일 -1.366%로 감쇠한다(TRADING_RULES §3). 오래 들고 있는 것 자체가 손실이다.

  ★ 5. 민감도 — 어느 쪽으로 보정해도 현행을 못 넘는다.
       + 5일 상한   : -1.517 → -1.002 (개선 폭 최대, 그래도 현행보다 1.19%p 낮음)
       + 손절 -6%   : -1.517 → -1.105
       + ②에 +7% 활성선 : -1.517 → **-1.991 (더 나빠진다)**
         활성선을 붙이면 조기 절반매도가 사라져 하방이 더 노출된다. 역설적으로 명세 그대로의
         ②(활성 조건 없음)가 그중 덜 나쁜 해석이다.

  ★ 6. 또 같은 서명이다 — '신규 (②는 +7%) +5일상한'은 중앙값 -0.576 / 승률 46.0%로 전 변형 중
       가장 좋은데 평균은 -1.011이다. 강세에 파는 규칙은 중앙값·승률을 올리고 평균을 깎는다.
       트레일링·급등매도+재매수에 이어 네 번째 확인이다.

⚠️ 시총 700억·reserved 교집합 미재현, 생존편향 포함 — 절대 수치가 아니라 규칙 간 비교만 볼 것.

사용법:
    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe auto_trading/backtest/exit_chandelier_test.py
    ... --limit 400
"""
import argparse
import os
import sys
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from auto_trading.backtest import fire_backtest_regen as R                 # noqa: E402
from auto_trading.backtest import strategy_matrix as SM                    # noqa: E402
from auto_trading.backtest.entry_threshold_test import CLOSE_POS_MIN, STOP  # noqa: E402

ROUND_TRIP = 0.21
ATR_N = 14
ATR_MULT = 3.0
TRAIL_DROP = 0.05      # ② 최고가 대비 -5%
TAKE_PROFIT = 0.20     # ③ 진입가 +20%
HARD_CAP = 40          # 시간상한 없는 변형의 백테스트 종료 지점(거래일)


def atr_wilder(high, low, close, n=ATR_N):
    """Wilder ATR. 첫 n개는 NaN."""
    prev = np.r_[np.nan, close[:-1]]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev), np.abs(low - prev)))
    out = np.full(len(tr), np.nan)
    if len(tr) <= n:
        return out
    out[n] = np.nanmean(tr[1:n + 1])
    for i in range(n + 1, len(tr)):
        out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return out


def sim_new(d, i, atr, use_chand=True, use_trail=True, use_tp=True,
            max_hold=HARD_CAP, hard_stop=None, trail_arm=0.0):
    """신규 청산안 시뮬레이션. (수익률%, 보유일, 청산사유, 잘렸는지) 반환.

    remaining은 1.0을 1포지션으로 본다(실제 주 수는 사이징이 결정하므로 무관).
    """
    op, hi, lo, cl = d['op'], d['hi'], d['lo'], d['cl']
    entry = cl[i]
    if entry <= 0:
        return None
    last = min(i + max_hold, len(cl) - 1)
    if last <= i:
        return None

    remaining = 1.0
    realized = []          # (비중, 수익률)
    reasons = []
    peak = entry           # 진입 후 최고가 (신호일 고가는 제외)
    armed_peak = None      # 트레일링이 마지막으로 발동한 시점의 최고가
    took_profit = False
    j = i

    for j in range(i + 1, last + 1):
        o, h, l = op[j], hi[j], lo[j]
        a = atr[j]

        # ③ 익절 +20% (고가 도달, 1회)
        if use_tp and not took_profit and h >= entry * (1 + TAKE_PROFIT):
            sell = remaining * 0.5
            realized.append((sell, TAKE_PROFIT * 100))
            remaining -= sell
            took_profit = True
            reasons.append('take20')

        peak = max(peak, h)

        # ② 트레일링 -5% (저가 터치, 절반, 고점 갱신 시 재무장)
        if use_trail and remaining > 1e-9 and peak >= entry * (1 + trail_arm):
            level = peak * (1 - TRAIL_DROP)
            rearmed = armed_peak is None or peak > armed_peak
            if rearmed and l <= level:
                fill = level if o > level else o
                sell = remaining * 0.5
                realized.append((sell, (fill / entry - 1) * 100))
                remaining -= sell
                armed_peak = peak
                reasons.append('trail5')

        # 하드 손절(변형에서만) — 잔여 전량
        if hard_stop is not None and remaining > 1e-9:
            hs = entry * (1 + hard_stop)
            if l <= hs:
                fill = hs if o > hs else o
                realized.append((remaining, (fill / entry - 1) * 100))
                remaining = 0.0
                reasons.append('stop6')
                break

        # ① 샹들리에 = 최고가 - 3*ATR (저가 이탈, 잔여 전량)
        if use_chand and remaining > 1e-9 and np.isfinite(a):
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
        # 청산 신호 없이 끝 → 마지막 날 종가. 데이터가 끝나서 잘린 건지 구분한다.
        truncated = (i + max_hold) > (len(cl) - 1)
        realized.append((remaining, (cl[j] / entry - 1) * 100))
        reasons.append('trunc' if truncated else 'time')

    ret = sum(w * r for w, r in realized)
    return ret, j - i, '|'.join(reasons), truncated


def sim_current_b(d, i, hold=5):
    """현행: 손절 -6%(1~hold-1일차 장중 저가) 아니면 hold일차 개장가 전량."""
    cl, lo, op = d['cl'], d['lo'], d['op']
    entry = cl[i]
    if i + hold >= len(cl):
        return None
    for k in range(1, hold):
        if lo[i + k] / entry - 1 <= STOP:
            return STOP * 100, k, 'stop6', False
    return (op[i + hold] / entry - 1) * 100, hold, 'max_hold', False


def sim_current_a(d, i):
    """현행 이전(트레일링 15일)."""
    res = R.simulate_exit(d['df'][SM.OHLC], i, d['cl'][i], 15)
    if res is None:
        return None
    trunc = res.get('exit') == 'truncated' or 'truncated' in str(res.get('exit_seq', ''))
    return res['ret_pct'], res.get('days', 0), str(res.get('exit', '')), trunc


VARIANTS = [
    ('현행 B: 손절-6%+5일',      lambda d, i, a: sim_current_b(d, i)),
    ('현행 A: 트레일링15일',      lambda d, i, a: sim_current_a(d, i)),
    ('신규 ①만(샹들리에)',        lambda d, i, a: sim_new(d, i, a, use_trail=False, use_tp=False)),
    ('신규 ①+②',                lambda d, i, a: sim_new(d, i, a, use_tp=False)),
    ('신규 ①+②+③ (요청안)',      lambda d, i, a: sim_new(d, i, a)),
    ('신규 ①+②+③ +5일상한',      lambda d, i, a: sim_new(d, i, a, max_hold=5)),
    ('신규 ①+②+③ +손절-6%',      lambda d, i, a: sim_new(d, i, a, hard_stop=STOP)),
    ('신규 ②+③만(샹들리에 없음)', lambda d, i, a: sim_new(d, i, a, use_chand=False)),
    # ②에 활성 조건이 없으면 최고가=진입가 상태에서 -5%에 바로 발동한다(실측 첫 사유의 95.8%).
    # 현행 트레일링의 활성선(+7%)을 붙여 그 해석 차이가 결과를 만드는지 분리한다.
    ('신규 ①+②+③ (②는 +7%부터)', lambda d, i, a: sim_new(d, i, a, trail_arm=0.07)),
    ('신규 (②는 +7%) +5일상한',    lambda d, i, a: sim_new(d, i, a, trail_arm=0.07, max_hold=5)),
]


def build(limit: Optional[int] = None):
    store, mkt, market_ret5 = SM.load_store(limit)
    print('청산 시뮬레이션...', flush=True)
    rows = []
    for n, (code, d) in enumerate(store.items(), 1):
        if n % 500 == 0:
            print(f'  ... {n}/{len(store)}', flush=True)
        # ATR은 종목당 한 번만
        d = dict(d)
        d['hi'] = d['df']['고가'].astype(float).to_numpy()
        atr = atr_wilder(d['hi'], d['lo'], d['cl'])

        base, chg, cpos = d['base'], d['chg'], d['cpos']
        cf = cpos >= CLOSE_POS_MIN
        groups = {'S1': base & (chg >= 3.0)}
        m = mkt.get(code)
        if m in market_ret5:
            rel = (d['ret5'] - market_ret5[m].reindex(d['idx'])).to_numpy()
            groups['S2'] = (base & (chg >= 2.0)
                            & (rel >= SM.REL_STRENGTH_LO) & (rel <= SM.REL_STRENGTH_HI))

        for gname, sig in groups.items():
            if not sig.any():
                continue
            sd = SM.signal_days(sig)
            for i in np.flatnonzero(sig & (sd == 1) & cf):
                rec = {'D': d['idx'][i], 'group': gname}
                ok = False
                for vname, fn in VARIANTS:
                    r = fn(d, i, atr)
                    if r is None or r[3]:      # None 또는 truncated 제외
                        rec[vname] = np.nan
                        rec[vname + '_h'] = np.nan
                    else:
                        rec[vname] = r[0]
                        rec[vname + '_h'] = r[1]
                        rec[vname + '_r'] = r[2]
                        ok = True
                if ok:
                    rows.append(rec)
    return pd.DataFrame(rows)


def report(X, group, title):
    S = X[X['group'] == group]
    years = sorted(S['D'].dt.year.unique())
    hdr = (f'{"청산 규칙":<26}{"건수":>8}{"기대수익%":>11}{"중앙%":>9}{"승률":>8}{"보유일":>8}'
           + ''.join(f'{y:>9}' for y in years))
    print('=' * len(hdr))
    print(title)
    print('=' * len(hdr))
    print(hdr)
    print('-' * len(hdr))
    out = []
    for vname, _ in VARIANTS:
        s = S[S[vname].notna()]
        if len(s) < 200:
            out.append((float('-inf'), vname, len(s), None))
            continue
        exp = s[vname].mean() - ROUND_TRIP
        by_y = s.groupby(s['D'].dt.year)[vname].mean()
        out.append((exp, vname, len(s),
                    (s[vname].median(), (s[vname] > 0).mean() * 100, s[vname + '_h'].mean(),
                     [by_y.get(y, float('nan')) - ROUND_TRIP for y in years])))
    out.sort(key=lambda r: -r[0])
    for exp, name, n, extra in out:
        if extra is None:
            print(f'{name:<26}{n:>8,}   (표본부족)')
            continue
        med, win, hold, ys = extra
        print(f'{name:<26}{n:>8,}{exp:>11.3f}{med:>9.3f}{win:>7.1f}%{hold:>8.2f}'
              + ''.join(f'{v:>9.3f}' for v in ys))
    print()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=None)
    args = ap.parse_args()

    X = build(limit=args.limit)
    print(f'\n총 {len(X):,}건\n')
    report(X, 'S1', 'S1 진입(현행 라이브: signal_days=1, 등락률>=3%, 종가위치>=0.6)')
    report(X, 'S2', 'S2 진입(상대강도 밴드) — 결론이 진입 집단에 의존하는지 확인')

    # 청산 사유 분포 — 어느 항목이 실제로 발동하는지
    col = '신규 ①+②+③ (요청안)'
    S = X[(X['group'] == 'S1') & X[col].notna()]
    first = S[col + '_r'].str.split('|').str[0].value_counts()
    print('요청안의 첫 청산 사유 분포 (S1):')
    for k, v in first.items():
        print(f'  {k:<12}{v:>8,}건 ({v / len(S):>5.1%})')
    print(f'\n요청안 평균 보유 {S[col + "_h"].mean():.2f}일 / '
          f'현행 B {S["현행 B: 손절-6%+5일_h"].mean():.2f}일')


if __name__ == '__main__':
    main()
