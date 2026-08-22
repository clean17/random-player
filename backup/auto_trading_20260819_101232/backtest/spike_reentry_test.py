# -*- coding: utf-8 -*-
"""급등 시 매도 → 되밀리면 재매수 전략 검증 (2026-08-18 작성).

질문: "급등했을 때 팔고 저가로 내려오면 다시 사는 걸 자동화할 수 없나?"
계기: 2026-08-18 후성(093370)이 장중 +18.9%까지 갔다가 +4%대로 되밀렸다.

트레일링과 뭐가 다른가: 트레일링도 '급등하면 판다'였고 3년 검증에서 4개 연도 전부 졌다
(exit_validation_3y.py: 트레일링+5일 -0.768% vs 손절-6%+5일 +0.065%, 비용후).
다만 트레일링에는 '판 뒤 되사서 계속 보유'가 없었다. 여기서는 그 재진입까지 넣어 측정한다.

━━━ 비교 규칙 ━━━
  A (현행)  : 손절 -6%(장중 저가) 또는 5영업일 종가 청산
  B (급등매도+재매수) : A에 더해, 장중 고가가 평단 대비 +SPIKE% 터치하면 전량 매도.
              같은 날 종가가 매도가 대비 -REBUY% 이상 밀려 있으면 그 종가에 재매수하고
              새 평단으로 계속 보유(5일 시계는 유지). 안 밀렸으면 현금으로 남는다.

━━━ 일봉으로 재현할 때의 가정 ━━━
  1. 매도는 트리거 가격에 체결된다고 본다 — 30초 잡은 관측 시점 가격에 팔므로 실제로는
     이보다 나쁘다. 즉 이 시뮬레이션은 B에 유리한(낙관) 방향이다.
  2. 재매수는 그날 종가. 고가가 종가보다 먼저 나오는 건 항상 참이므로 경로상 실행 가능하다.
  3. 같은 날 손절선과 급등선이 둘 다 걸리면 손절을 먼저 적용한다(비관 방향).
  4. 왕복비용 0.21%를 라운드트립마다 부과한다 — 재매수하면 왕복이 하나 더 붙는다.
     실계좌 추정치(TRADING_RULES §8-4: 수수료 0.015%x2 + 거래세 0.18%).

⚠️ 근본 한계: 일봉은 하루 안의 순서를 모른다. 이 검증이 답할 수 있는 건 '고가·종가만으로
   구성 가능한 경로'뿐이고, 실제 30초 잡이 겪는 일중 진동은 재현하지 못한다.
   진짜로 검증하려면 분봉 수집부터 해야 한다.

━━━ 결과 (2026-08-18, pkl 2,858종목 3년, 신호 31,499건, 비용후 %) ━━━

  A. 현행(손절-6%+5일)      -0.028   승률 37.2%   2023 -0.195 / 2024 -0.177 / 2025 +0.303 / 2026 -0.100
  B. 급등 8%/되밀림3%       -0.274   승률 43.5%   재진입 0.07회/건
  B. 급등10%/되밀림3%       -0.166   승률 41.5%   재진입 0.07회/건
  B. 급등12%/되밀림3%       -0.075   승률 40.4%   재진입 0.06회/건
  B. 급등15%/되밀림5%       +0.001   승률 39.3%   재진입 0.03회/건

  ★ 단조 관계다 — 급등 트리거를 높일수록 A에 수렴한다. 15%면 거의 발동하지 않아서
    사실상 A와 같아진다. 즉 '실제로 발동하는 모든 설정이 현행보다 나쁘다'.
    유일하게 안 나쁜 설정은 아무 일도 안 하는 설정이다.

  ★ 트레일링과 정확히 같은 서명: 승률은 오르고(37.2% → 43.5%) 평균은 떨어진다.
    큰 승리를 작은 승리로 바꾸는 것이다.

  ★ 재진입은 거의 일어나지 않는다(0.03~0.07회/건). 급등 트리거가 걸리면서 '같은 날 종가가
    매도가 대비 3~5% 아래'까지 밀리는 조합이 드물기 때문. 그래서 매도만 발동해 상승을
    끊고, 되사서 만회하는 일은 사실상 없다.

  같은 방향의 독립 검증 3건 — 전부 '강세에 파는' 규칙이고 전부 졌다:
    1. 트레일링(고점-5%p)        -0.768 vs +0.065   (exit_validation_3y.py)
    2. 목표가 사다리(10/15/20%)  비활성화됨          (TRADING_RULES §3-4)
    3. 급등매도+재매수           위 표

⚠️ 절대 수치를 다른 스크립트와 비교하지 말 것. 여기 A(-0.028)와 exit_validation_3y의
   '단순5일+손절6%'(+0.065)는 신호 모집단이 다르다(문턱 3% + 종가위치 필터 vs 문턱 2% 무필터).
   이 표 안에서 A vs B만 같은 조건이다.

사용법:
    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe auto_trading/backtest/spike_reentry_test.py
    ... --limit 300
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

from auto_trading.kiwoom_fire_strategy import PKL_DIR                 # noqa: E402
from auto_trading.backtest.track_compare import prep                  # noqa: E402
from auto_trading.backtest.entry_threshold_test import (              # noqa: E402
    CLUSTER_GAP, CLOSE_POS_MIN, STOP, MAX_HOLD,
)

INTEREST_MIN_RATE = 3.0
ROUND_TRIP = 0.21    # % — 실계좌 추정 왕복비용


def sim_current(close, low, i):
    """규칙 A. (총수익%, 라운드트립 수) 반환."""
    entry = close[i]
    for k in range(1, MAX_HOLD + 1):
        j = i + k
        if j >= len(close):
            j = len(close) - 1
            return (close[j] / entry - 1) * 100, 1
        if low[j] / entry - 1 <= STOP:
            return STOP * 100, 1
    j = min(i + MAX_HOLD, len(close) - 1)
    return (close[j] / entry - 1) * 100, 1


def sim_spike(close, high, low, i, spike, rebuy):
    """규칙 B. (총수익%, 라운드트립 수, 재진입 횟수) 반환.

    구간별 수익률을 곱해서 누적한다 — 재매수로 평단이 바뀌므로 단순 합산이 아니다.
    """
    basis = close[i]
    growth = 1.0
    trips = 1
    reentries = 0

    for k in range(1, MAX_HOLD + 1):
        j = i + k
        if j >= len(close):
            break
        # 3) 손절을 먼저 본다 (비관 방향)
        if low[j] / basis - 1 <= STOP:
            growth *= (1 + STOP)
            return (growth - 1) * 100, trips, reentries
        # 급등 트리거
        if high[j] / basis - 1 >= spike:
            sell_px = basis * (1 + spike)
            growth *= (1 + spike)
            close_px = close[j]
            if close_px <= sell_px * (1 - rebuy):
                basis = close_px          # 되밀렸으니 재매수
                trips += 1
                reentries += 1
                continue
            return (growth - 1) * 100, trips, reentries   # 안 밀렸으면 현금 보유
    j = min(i + MAX_HOLD, len(close) - 1)
    if j > i:
        growth *= close[j] / basis
    return (growth - 1) * 100, trips, reentries


def build_signals(limit: Optional[int] = None):
    files = [f for f in os.listdir(PKL_DIR) if f.endswith('.pkl')]
    if limit:
        files = files[:limit]
    out = []
    for n, fname in enumerate(files, 1):
        if n % 500 == 0:
            print(f'  ... {n}/{len(files)}', flush=True)
        d = prep(os.path.join(PKL_DIR, fname))
        if d is None:
            continue
        base = d['base'].to_numpy()
        chg = d['chg'].to_numpy()
        cpos = d['close_pos'].to_numpy()
        hits = np.flatnonzero(base & (chg >= INTEREST_MIN_RATE))
        if len(hits) == 0:
            continue
        firsts = [hits[0]]
        for a, b in zip(hits[:-1], hits[1:]):
            if b - a > CLUSTER_GAP:
                firsts.append(b)
        close = d['close'].to_numpy()
        high = d['high'].to_numpy()
        low = d['low'].to_numpy()
        idx = d.index
        for i in firsts:
            if i + 1 >= len(close) or close[i] <= 0 or cpos[i] < CLOSE_POS_MIN:
                continue
            out.append((idx[i], close, high, low, i))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=None)
    args = ap.parse_args()

    print('신호 생성 중...', flush=True)
    sigs = build_signals(limit=args.limit)
    print(f'신호 {len(sigs):,}건\n')

    base_rows = []
    for D, close, high, low, i in sigs:
        r, t = sim_current(close, low, i)
        base_rows.append({'D': D, 'ret': r - ROUND_TRIP * t})
    A = pd.DataFrame(base_rows)
    years = sorted(A['D'].dt.year.unique())

    def line(name, df, extra=''):
        by_y = df.groupby(df['D'].dt.year)['ret'].mean()
        print(f'{name:<22}{df["ret"].mean():>10.3f}{(df["ret"] > 0).mean() * 100:>8.1f}%'
              + ''.join(f'{by_y.get(y, float("nan")):>10.3f}' for y in years)
              + f'  {extra}')

    hdr = (f'{"규칙":<22}{"비용후%":>10}{"승률":>9}'
           + ''.join(f'{y:>10}' for y in years))
    print('=' * (len(hdr) + 22))
    print('급등매도 후 재매수 (SPIKE=급등 트리거, REBUY=매도가 대비 되밀림 폭)')
    print('=' * (len(hdr) + 22))
    print(hdr + '  재진입율')
    print('-' * (len(hdr) + 22))
    line('A. 현행(손절+5일)', A)
    print('-' * (len(hdr) + 22))

    for spike in (0.08, 0.10, 0.12, 0.15):
        for rebuy in (0.03, 0.05):
            rows = []
            re_tot = 0
            for D, close, high, low, i in sigs:
                r, t, re = sim_spike(close, high, low, i, spike, rebuy)
                rows.append({'D': D, 'ret': r - ROUND_TRIP * t})
                re_tot += re
            B = pd.DataFrame(rows)
            line(f'B. 급등{spike:.0%}/되밀림{rebuy:.0%}', B,
                 extra=f'{re_tot / len(sigs):.2f}회/건')
        print('-' * (len(hdr) + 22))


if __name__ == '__main__':
    main()
