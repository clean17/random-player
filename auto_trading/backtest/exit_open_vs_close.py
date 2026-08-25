# -*- coding: utf-8 -*-
"""보유상한 청산: 5일차 시가 매도 vs 종가 매도 (2026-08-18 작성).

계기: 라이브와 백테스트가 어긋나 있다는 걸 발견했다.
  백테스트  : close[i+5] — 5거래일 뒤 **종가** 청산 가정
              (slot_sizing_test / cash_ratio_test / track_compare 전부)
  라이브    : 조건이 `held >= MAX_HOLD_DAYS`라 그날 첫 사이클에 바로 걸린다.
              09:00 KRX 개장 직후 시장가 → 실질 **시가** 청산
              (NXT 프리마켓은 시장가 거부라 08:00엔 못 나간다 — TRADING_RULES §3)

네 규칙을 같은 신호에 태워 차이를 분해한다.
  A. 종가[i+5]  손절 -6%를 5일차까지 본다      ← 백테스트 가정
  B. 시가[i+5]  손절 -6%를 4일차까지 본다      ← 라이브 실제
  C. 종가[i+4]  손절 -6%를 4일차까지 본다      ← 참고(하루 일찍 종가 청산)
  D. 시가[i+4]  손절 -6%를 3일차까지 본다      ← 창에 공휴일이 하나 낀 경우의 라이브 동작

━━━ 결과 (2026-08-18, pkl 2,858종목 3년, 신호 31,401건, 왕복비용 0.21% 차감) ━━━

  청산 방식                비용후%    중앙%    승률   2023    2024    2025    2026
  A. 종가[5일차] (백테)    -0.021   -2.634  38.0%  -0.189  -0.169  +0.302  -0.080
  B. 시가[5일차] (라이브)  +0.113   -1.905  39.5%  +0.001  -0.016  +0.339  +0.102
  C. 종가[4일차]           -0.071   -1.952  38.9%  -0.235  -0.138  +0.189  -0.161
  D. 시가[4일차] (공휴일)  +0.142   -1.282  41.5%  +0.027  +0.001  +0.396  +0.108

  ★ 라이브(B)가 백테스트 가정(A)보다 +0.134%p 낫다. 4개 연도 전부. 즉 지금까지의 모든
    백테스트가 라이브 성과를 과소평가하고 있었다(불리한 방향이 아니라 유리한 방향의 괴리).

  분해:  종가[4일차] -0.071  --오버나이트 갭 +0.184-->  시가[5일차] +0.113
                            --5일차 세션 -0.134-->     종가[5일차] -0.021

  4일차까지 손절 안 된 19,622건(62.5%) 기준:
    오버나이트 갭(4일차 종가→5일차 시가) 평균 +0.262% / 중앙 +0.000% / 플러스 47.9%
    5일차 세션(시가→종가)              평균 -0.207% / 중앙 -0.391% / 플러스 42.0%
  → 갭은 중앙값 0인 우측 꼬리(갭상승이 갭하락보다 큼)이고, 5일차 낮 세션은 일관되게 마이너스다.
    아침에 팔면 갭은 먹고 낮 하락은 피한다. 이게 B > A의 정체다.

  ★ D > B — 공휴일로 하루 일찍 나가는 게 오히려 낫다. `_held_business_days`가 월~금만 세는
    것은 고칠 필요가 없다(고치면 성과가 떨어진다). 기존 주석의 "늦게 파는 것보다 안전한
    방향"은 안전할 뿐 아니라 유리한 것으로 실측됐다.

  ※ D > B를 보고 MAX_HOLD_DAYS 5→4를 검증했으나 **기각됐다**(max_hold_sweep.py, 2026-08-18).
    H를 2~7로 훑으면 건당이 전부 +0.088~+0.137 구간이고 단조성이 없다. 여기서 보이는
    D > B 차이는 그 노이즈 폭 안이다. MAX_HOLD_DAYS는 5를 유지한다.

⚠️ 손절 체결가는 정확히 -6%로 잡는다(기존 harness 관례). 갭하락으로 손절선을 건너뛴 날은
   실제로 더 나쁘게 체결되므로 네 규칙 모두 그만큼 낙관적이다(차이 비교에는 대체로 상쇄).
⚠️ 시총 700억·reserved 교집합 미재현. 절대 수치가 아니라 규칙 간 차이만 볼 것.
⚠️ pkl에 시가/종가가 0원인 불량 행이 있어 청산 시점 가격이 0이면 제외한다(31,436 → 31,401건).

사용법:
    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe auto_trading/backtest/exit_open_vs_close.py
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

from auto_trading.kiwoom_fire_strategy_mock import PKL_DIR                 # noqa: E402
from auto_trading.backtest.entry_threshold_test import (              # noqa: E402
    TRADING_VALUE, MIN_CLOSE, CLUSTER_GAP, CLOSE_POS_MIN,
    STOP, MAX_HOLD, OVERHEAT_MULT,
)

INTEREST_MIN_RATE = 3.0
ROUND_TRIP = 0.21


def prep_ohlc(path):
    """entry_threshold_test.scan_one과 같은 게이트를 쓰되 시가까지 남긴다."""
    try:
        df = pd.read_pickle(path)
    except Exception:
        return None
    need = ['시가', '고가', '저가', '종가', '거래량', '등락률']
    if not all(c in df.columns for c in need):
        return None
    df = df[need].dropna()
    if len(df) < 60:
        return None
    df.index = pd.to_datetime(df.index)

    close = df['종가'].astype(float)
    tv = df['거래량'].astype(float) * close
    ma5 = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()
    ma5_chg = (ma5 / ma5.shift(1) - 1) * 100
    avg5 = tv.shift(1).rolling(5).mean()
    box = (close.shift(1).rolling(10).max() / close.shift(1).rolling(10).min() - 1) * 100
    high, low = df['고가'].astype(float), df['저가'].astype(float)

    base = ((close >= MIN_CLOSE) & (tv >= TRADING_VALUE)
            & ~((ma5 < ma20) & (ma5_chg < -3)) & ma20.notna()
            & ((box < 6) | ~((avg5 > 0) & (tv >= OVERHEAT_MULT * avg5))))
    close_pos = np.where(high > low, (close - low) / (high - low), 1.0)
    return (df.index, df['시가'].astype(float).to_numpy(), high.to_numpy(),
            low.to_numpy(), close.to_numpy(), df['등락률'].astype(float).to_numpy(),
            base.to_numpy(), close_pos)


def run(limit: Optional[int] = None):
    files = [f for f in os.listdir(PKL_DIR) if f.endswith('.pkl')]
    if limit:
        files = files[:limit]
    rows = []
    for n, fname in enumerate(files, 1):
        if n % 500 == 0:
            print(f'  ... {n}/{len(files)}', flush=True)
        p = prep_ohlc(os.path.join(PKL_DIR, fname))
        if p is None:
            continue
        idx, op, hi, lo, cl, chg, base, cpos = p
        hits = np.flatnonzero(base & (chg >= INTEREST_MIN_RATE))
        if len(hits) == 0:
            continue
        firsts = [hits[0]]
        for a, b in zip(hits[:-1], hits[1:]):
            if b - a > CLUSTER_GAP:
                firsts.append(b)

        for i in firsts:
            if cpos[i] < CLOSE_POS_MIN or i + MAX_HOLD >= len(cl) or cl[i] <= 0:
                continue
            # 보유구간에 0원 시가/종가가 섞인 행이 있다(pkl 불량). 그대로 두면 B가 -100%로
            # 계산돼 평균을 끌어내린다. 청산 시점에 쓰는 가격만 검사한다.
            if (op[i + MAX_HOLD] <= 0 or cl[i + MAX_HOLD] <= 0
                    or cl[i + MAX_HOLD - 1] <= 0 or op[i + MAX_HOLD - 1] <= 0):
                continue
            entry = cl[i]

            # 손절이 k일차에 걸리는지 (장중 저가 기준)
            stop_day = None
            for k in range(1, MAX_HOLD + 1):
                if lo[i + k] / entry - 1 <= STOP:
                    stop_day = k
                    break

            # A: 5일차까지 손절 본 뒤 종가[i+5]
            a_ret = STOP * 100 if stop_day is not None else (cl[i + MAX_HOLD] / entry - 1) * 100
            # B: 4일차까지 손절 본 뒤 시가[i+5]
            if stop_day is not None and stop_day <= MAX_HOLD - 1:
                b_ret = STOP * 100
            else:
                b_ret = (op[i + MAX_HOLD] / entry - 1) * 100
            # C: 4일차까지 손절 본 뒤 종가[i+4]
            if stop_day is not None and stop_day <= MAX_HOLD - 1:
                c_ret = STOP * 100
            else:
                c_ret = (cl[i + MAX_HOLD - 1] / entry - 1) * 100
            # D: 시가[i+4] — 창에 공휴일이 하나 끼었을 때의 라이브 동작.
            #    _held_business_days가 월~금만 세므로 held=5가 실제 4거래일째에 도달한다.
            if stop_day is not None and stop_day <= MAX_HOLD - 2:
                d_ret = STOP * 100
            else:
                d_ret = (op[i + MAX_HOLD - 1] / entry - 1) * 100

            rows.append({
                'D': idx[i], 'a': a_ret, 'b': b_ret, 'c': c_ret, 'd': d_ret,
                # 오버나이트 갭: 4일차 종가 → 5일차 시가
                'gap': (op[i + MAX_HOLD] / cl[i + MAX_HOLD - 1] - 1) * 100,
                # 5일차 하루 세션: 시가 → 종가
                'day5': (cl[i + MAX_HOLD] / op[i + MAX_HOLD] - 1) * 100,
                'stopped_by4': stop_day is not None and stop_day <= MAX_HOLD - 1,
                'stopped_d5': stop_day == MAX_HOLD,
            })
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=None)
    args = ap.parse_args()

    print('스캔 중...', flush=True)
    X = run(limit=args.limit)
    print(f'신호 {len(X):,}건\n')
    years = sorted(X['D'].dt.year.unique())

    hdr = (f'{"청산 방식":<28}{"비용후%":>10}{"중앙%":>9}{"승률":>8}'
           + ''.join(f'{y:>9}' for y in years))
    print('=' * len(hdr))
    print('보유상한 청산 시점 비교 (왕복비용 0.21% 차감)')
    print('=' * len(hdr))
    print(hdr)
    print('-' * len(hdr))
    labels = [('A. 종가[5일차]  (백테스트 가정)', 'a'),
              ('B. 시가[5일차]  (라이브 실제)', 'b'),
              ('C. 종가[4일차]  (참고)', 'c'),
              ('D. 시가[4일차]  (공휴일 1일 낀 경우)', 'd')]
    for lab, col in labels:
        by_y = X.groupby(X['D'].dt.year)[col].mean()
        print(f'{lab:<28}{X[col].mean() - ROUND_TRIP:>10.3f}{X[col].median():>9.3f}'
              f'{(X[col] > 0).mean() * 100:>7.1f}%'
              + ''.join(f'{by_y.get(y, float("nan")) - ROUND_TRIP:>9.3f}' for y in years))
    print()

    print(f'B - A (라이브가 백테스트보다 나은 폭) : {X["b"].mean() - X["a"].mean():+.3f}%p')
    print(f'B - C (오버나이트 갭 기여)            : {X["b"].mean() - X["c"].mean():+.3f}%p')
    print(f'A - B (5일차 세션 기여, 음수면 손해)  : {X["a"].mean() - X["b"].mean():+.3f}%p')
    print()

    # 청산까지 살아남은 건만 봐야 갭/세션 효과가 희석되지 않는다
    S = X[~X['stopped_by4']]
    print(f'4일차까지 손절 안 된 건 {len(S):,}건 ({len(S) / len(X):.1%}) — 이 건들만 시점 차이가 생긴다')
    print(f'  오버나이트 갭(4일차 종가→5일차 시가) 평균 {S["gap"].mean():+.3f}% / '
          f'중앙 {S["gap"].median():+.3f}% / 플러스 비율 {(S["gap"] > 0).mean():.1%}')
    print(f'  5일차 세션(시가→종가)            평균 {S["day5"].mean():+.3f}% / '
          f'중앙 {S["day5"].median():+.3f}% / 플러스 비율 {(S["day5"] > 0).mean():.1%}')
    print(f'  5일차에 손절선 터치 {X["stopped_d5"].sum():,}건 — A는 -6%로 잡고 B는 시가에 이미 나가 있다')


if __name__ == '__main__':
    main()
