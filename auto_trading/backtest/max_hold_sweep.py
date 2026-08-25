# -*- coding: utf-8 -*-
"""MAX_HOLD_DAYS 스윕 — 시가 청산 전제 (2026-08-18 작성).

계기: exit_open_vs_close.py에서 라이브가 '5일차 시가' 청산이라는 게 확인됐고, 그 전제에서
      4거래일(+0.142%)이 5거래일(+0.113%)보다 나았다. MAX_HOLD_DAYS 5→4를 따로 검증한다.

⚠️ exit_validation_3y.py의 '5일 > 3일'은 **종가 청산** 전제라 이 비교와 직접 이어지지 않는다.
   그 스크립트는 close[i+hold]로 청산했고, 라이브는 open[i+hold]에 나간다.

━━━ 시뮬레이션 (라이브 동작 그대로) ━━━
  손절 -6%를 1..H-1일차 장중 저가로 판정 → 걸리면 그날 청산
  안 걸리면 H일차 09:00 개장가(open[i+H])에 전량 청산
  (H일차 아침이 첫 사이클이므로 그날 장중 저가는 볼 기회가 없다)

  진입: 첫 신호일(6영업일 창) + 등락률>=3% + 종가위치>=0.6, 공통 게이트는 스캐너와 동일

건당 수익률과 포트폴리오 수익률을 같이 낸다 — 보유가 짧아지면 회전이 빨라져 같은 자본으로
더 자주 들어가므로, 건당 수치만으로는 판단할 수 없다.

━━━ 결과 (2026-08-18, pkl 2,858종목 3년, 신호 31,337건 — 모든 H에서 동일 집합) ━━━

  건당 (왕복비용 0.21% 차감)
   H   비용후%    중앙%    승률   평균보유   2023    2024    2025    2026
   2   +0.137   -0.388  44.4%   1.88   +0.142  +0.022  +0.304  +0.044
   3   +0.102   -0.751  43.4%   2.65   +0.084  -0.041  +0.336  -0.024
   4   +0.126   -1.282  41.5%   3.34   +0.030  -0.005  +0.391  +0.034
   5   +0.095   -1.905  39.5%   3.96   +0.004  -0.023  +0.337  +0.013   ← 현행
   6   +0.088   -2.651  38.3%   4.54   -0.061  -0.129  +0.469  +0.014
   7   +0.135   -3.554  37.2%   5.08   -0.014  -0.173  +0.576  +0.107

  ★ 결론: MAX_HOLD_DAYS를 바꿀 근거가 없다. 5를 유지한다.

  이유 1 — 건당 차이가 노이즈다. H 2~7이 전부 +0.088~+0.137 구간이고 단조성이 없다
    (H=7이 H=2와 사실상 같고, H=3이 H=4보다 낮다). H=4가 H=5를 4개 연도 전부 앞서긴 하지만
    폭이 +0.031%p로 곡선의 비단조 폭보다 작다.

  이유 2 — 포트폴리오 수치는 경로 노이즈가 지배해 쓸 수 없다.
    전체 2,858종목: H2 +508% / H3 +72.7 / H4 +30.6 / H5 +35.4 / H6 -26.7 / H7 -30.1
    600종목 부분집합: H2 +65.0% / H3 +9.5 / H5 +52.6 / H7 +10.9
    → 두 집합의 순서가 서로 뒤집힌다(H3 vs H5). 부트스트랩 표준편차도 22~38%p였다.
      건당은 평평한데 포트폴리오만 크게 갈리는 것 자체가 신호가 아니라 경로 효과라는 뜻이다.
      체결 건수는 H와 무관하게 ~3,100건으로 거의 같았다(슬롯5·후보7이 병목이라 회전이
      보유기간에 비례해 늘지 않는다) — 회전 가설도 성립하지 않는다.

  ⚠️ H=2·H=3의 큰 포트폴리오 수익은 오버나이트 갭을 반복 포획하는 데서 나오는데, 그게 실제로
     체결 가능한지는 일봉으로 검증할 수 없다. 09:00 시가는 동시호가로 결정되고 30초 잡의 첫
     사이클은 09:00:00이 아니며, 개장 직후 스프레드는 왕복 0.21% 가정보다 넓다.
     이 방향을 진지하게 보려면 분봉 수집과 실측 체결가 비교가 선행되어야 한다.

⚠️ 시총 700억·reserved 교집합 미재현. 절대 수치가 아니라 H 간 비교만 볼 것.

사용법:
    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe auto_trading/backtest/max_hold_sweep.py
    ... --bootstrap 25
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

from auto_trading.kiwoom_fire_strategy_mock import PKL_DIR                        # noqa: E402
from auto_trading.backtest.entry_threshold_test import (                     # noqa: E402
    CLUSTER_GAP, CLOSE_POS_MIN, STOP,
)
from auto_trading.backtest.exit_open_vs_close import prep_ohlc, ROUND_TRIP   # noqa: E402
from auto_trading.backtest import cash_ratio_test as CR                      # noqa: E402

INTEREST_MIN_RATE = 3.0
HOLDS = (2, 3, 4, 5, 6, 7)


def build(limit: Optional[int] = None):
    files = [f for f in os.listdir(PKL_DIR) if f.endswith('.pkl')]
    if limit:
        files = files[:limit]
    acc = {h: [] for h in HOLDS}
    maxh = max(HOLDS)

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
            # 모든 H를 같은 신호 집합에서 비교해야 하므로 최장 H까지 데이터가 있는 것만 쓴다
            if cpos[i] < CLOSE_POS_MIN or i + maxh >= len(cl) or cl[i] <= 0:
                continue
            if min(op[i + 1:i + maxh + 1]) <= 0 or min(cl[i + 1:i + maxh + 1]) <= 0:
                continue        # pkl 불량 행(0원) 제외
            entry = cl[i]

            for h in HOLDS:
                stop_day = None
                for k in range(1, h):          # H일차 아침에 나가므로 H-1일차까지만 손절 판정
                    if lo[i + k] / entry - 1 <= STOP:
                        stop_day = k
                        break
                if stop_day is not None:
                    ret, hold = STOP * 100, stop_day
                else:
                    ret, hold = (op[i + h] / entry - 1) * 100, h
                acc[h].append({'D': idx[i], 'entry': entry, 'close_pos': cpos[i],
                               'ret': ret, 'hold': hold})
    return {h: pd.DataFrame(v) for h, v in acc.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--bootstrap', type=int, default=0)
    ap.add_argument('--capital', type=int, default=1_990_000)
    args = ap.parse_args()

    print('스캔 중...', flush=True)
    tracks = build(limit=args.limit)
    n = len(tracks[HOLDS[0]])
    print(f'신호 {n:,}건 (모든 H에서 동일 집합)\n')
    years = sorted(tracks[HOLDS[0]]['D'].dt.year.unique())

    hdr = (f'{"MAX_HOLD":<12}{"비용후%":>10}{"중앙%":>9}{"승률":>8}{"평균보유":>9}'
           + ''.join(f'{y:>9}' for y in years))
    print('=' * len(hdr))
    print('건당 수익률 — 라이브 동작(H일차 개장가 청산), 왕복비용 0.21% 차감')
    print('=' * len(hdr))
    print(hdr)
    print('-' * len(hdr))
    for h in HOLDS:
        X = tracks[h]
        by_y = X.groupby(X['D'].dt.year)['ret'].mean()
        mark = '  ← 현행' if h == 5 else ''
        print(f'{h:<12}{X["ret"].mean() - ROUND_TRIP:>10.3f}{X["ret"].median():>9.3f}'
              f'{(X["ret"] > 0).mean() * 100:>7.1f}%{X["hold"].mean():>9.2f}'
              + ''.join(f'{by_y.get(y, float("nan")) - ROUND_TRIP:>9.3f}' for y in years) + mark)
    print()

    if args.bootstrap:
        CR.RATIOS = (0.65,)   # 현행 CASH_DEPLOY_RATIO 하나만
        for h in HOLDS:
            print(f'\n########## MAX_HOLD_DAYS = {h} ##########')
            CR.bootstrap(tracks[h], args.capital, slots=5, divisor=5,
                         pool=7, n_iter=args.bootstrap)


if __name__ == '__main__':
    main()
