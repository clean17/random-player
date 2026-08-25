# -*- coding: utf-8 -*-
"""진입 4집단 x 청산 2규칙 = 8가지 조합 기대수익 비교 (2026-08-18 작성).

판정 기준: **건당 기대수익(왕복비용 차감 후 평균 %)**. 연도별 일관성을 같이 낸다 —
레짐 게이트·청산 개선안 검증에서 '전체 평균은 좋아 보여도 한 해가 만든 착시'를 두 번 겪었다.

━━━ 진입 4집단 ━━━
  공통: 종가 매수(신호일 종가) · 스캐너 공통 게이트 · 종가위치 >= 0.6 · 다음날(D+1)부터 청산 평가
  signal_days = 최근 6영업일 창(i-6..i)의 신호일 수. 라이브 fire SQL의
               COUNT(DISTINCT created_at::date) + last_date=D 조건에 대응한다.

  S1  signal 전략 v1   : signal_days == 1,   등락률 >= 3%              (현행 라이브)
  S2  signal 전략 v2   : signal_days == 1,   등락률 >= 2% + 상대강도밴드 2.8~7.1%p
  F1  fire 2-3일 v1    : signal_days in 2,3, 등락률 >= 3%              (2026-08-14 이전 규칙)
  F2  fire 2-3일 v2    : signal_days in 2,3, 등락률 >= 2% + 상대강도밴드

  v1/v2의 등락률 문턱이 다른 건 스캐너 설정이 실제로 그렇기 때문이다
  (2_finding_stocks_with_increased_volume=3% / 2_finding_stocks_advanced=2%).

━━━ 청산 2규칙 ━━━
  A 트레일링 : fire_backtest_regen.simulate_exit — 손절 -6% + 트레일링(활성 +7%/gap 5%p/
               보호선 +3%/3분할) + 정체보호 6%p + 시간상한 15일. 2026-08-14 이전 운영 규칙.
  B 5일보유  : 손절 -6%(1~4일차 장중 저가) + 5일차 개장가 전량. 현행 라이브 동작
               (exit_open_vs_close.py에서 '5일차 시가'가 실제 체결 시점임을 확인)

  왕복비용 0.21%를 일괄 차감한다. 트레일링의 3분할 매도는 비용을 늘리지 않는다 —
  국내 수수료·거래세는 전부 거래대금 비례라 나눠 팔아도 총액이 같다.

⚠️ 재현 한계 (8조합 전부에 동일하게 적용되므로 상대 비교는 성립)
  - 시가총액 700억 / 평균거래대금 40억 필터 미재현 (pkl에 시총 없음)
  - reserved 교집합 미재현 → '전 종목을 체크했다면'의 상한선
  - 생존편향: 상장폐지 종목이 pkl에 없다
  - 트레일링은 same_day_trigger=True(비관 극단)가 기본. 낙관 극단도 같이 출력한다.

━━━ 결과 (2026-08-18, pkl 2,858종목 / 2023-03 ~ 2026-08, 92,309건) ━━━

  조합                        건수    기대수익%   중앙%    승률   2023    2024    2025    2026
  F1 fire2-3 v1 / B 5일보유  38,922   +0.356   -3.438  37.8%  -0.087  -0.099  +0.643  +0.765
  S2 signal  v2 / B 5일보유  16,799   +0.232   -1.408  41.6%  +0.069  -0.106  +0.442  +0.603
  F2 fire2-3 v2 / B 5일보유   5,020   +0.190   -1.448  42.1%  -0.120  -0.236  +0.402  +0.743
  S1 signal  v1 / B 5일보유  31,406   +0.187   -1.899  39.5%  +0.061  +0.021  +0.397  +0.271  ← 현행
  S1 signal  v1 / A 트레일링 31,395   -0.858   -4.181  40.1%
  F1 fire2-3 v1 / A 트레일링 38,894   -0.880   -6.000  39.4%
  S2 signal  v2 / A 트레일링 16,774   -0.893   -3.644  41.5%
  F2 fire2-3 v2 / A 트레일링  5,012   -0.966   -5.802  40.4%

  ★ 1. 청산이 진입을 압도한다. B 4개가 전부 +0.187~+0.356, A 4개가 전부 -0.858~-0.966.
       청산 차이 ~1.2%p vs 진입 차이 최대 0.17%p. **트레일링은 어떤 진입과 붙여도 진다.**
       낙관 극단(same_day_trigger=False)으로 트레일링에 최대한 유리하게 잡아도 +0.15~+0.30이라
       B의 비관 추정치를 못 넘는다.

  ★ 2. 평균 1위는 F1(+0.356)이지만 **연도별 일관성에서 탈락한다.**
       이 프로젝트의 판정 기준은 '개선안은 모든 해에서 현행보다 높아야 한다'(exit_validation_3y).
         F1 vs S1 : 2/4 (2023 -0.087<+0.061, 2024 -0.099<+0.021 패)
         S2 vs S1 : 3/4 (2024만 패)
         F2 vs S1 : 2/4
       **현행 S1만 4개 연도 전부 플러스다.** F1의 +0.356은 2025~2026이 만든 값이다.

  ★ 3. F1은 분포가 가장 나쁘다 — 중앙 -3.438 / 승률 37.8%로 네 B조합 중 최악인데 평균만 높다.
       오른쪽 꼬리에 의존하는 복권형이라 복리·노출을 태우면 평균대로 안 나온다
       (cash_ratio_test/max_hold_sweep에서 확인된 산술평균-기하평균 괴리).

  ★ 4. 상대강도 밴드(v2)의 효과가 진입 집단에 따라 뒤집힌다.
       signal_days=1 : S1 +0.187 → S2 +0.232  (도움)
       signal_days2-3: F1 +0.356 → F2 +0.190  (해로움)
       v2를 쓴다면 signal 전략과만 붙여야 한다.

  ★ 5. v2의 우위가 청산 규칙에 따라 줄어든다. track_compare(종가 청산)에서는 v1 -0.013 vs
       v2 +0.174로 +0.187%p 차이였는데, 라이브 청산(개장가)에서는 +0.045%p로 좁혀진다.
       개장가 청산의 이득을 v1이 훨씬 많이 가져간다(+0.200 vs +0.058).

  ★ 6. 종가위치>=0.6 필터는 F2를 뺀 셋에서 도움이 된다 (청산 B 기준)
       S1 +0.007→+0.187 / S2 +0.110→+0.232 / F1 +0.290→+0.356 / F2 +0.309→+0.190

  ⚠️ 미해결 충돌: entry_timing.py는 '신호 차수가 올라갈수록 성과가 단조 감소'(1번째 +0.431 /
     3번째 -0.043)를 근거로 2026-08-14에 signal_days=1로 바꿨다. 여기서는 F1(2~3차)이
     S1(1차)보다 평균이 높다. 조건이 다르다 — entry_timing은 DB 신호(타겟 혼재)·3일 고정보유·
     종가위치 미적용·1년이고, 여기는 pkl 재현·실제 청산규칙·종가위치 적용·3년이다.
     **어느 쪽이 맞는지 정리되기 전에는 signal_days를 되돌리지 말 것.**

사용법:
    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe auto_trading/backtest/strategy_matrix.py
    ... --limit 400        (빠른 확인)
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

from auto_trading.kiwoom_fire_strategy_mock import PKL_DIR                     # noqa: E402
from auto_trading.backtest import fire_backtest_regen as R                # noqa: E402
from auto_trading.backtest.entry_threshold_test import (                  # noqa: E402
    TRADING_VALUE, MIN_CLOSE, CLUSTER_GAP, CLOSE_POS_MIN, STOP, OVERHEAT_MULT,
)
from auto_trading.backtest.track_compare import (                         # noqa: E402
    load_market_map, REL_STRENGTH_LO, REL_STRENGTH_HI,
)

ROUND_TRIP = 0.21      # % 실계좌 추정 왕복비용
HOLD_B = 5             # 청산 B의 보유 상한
TRAIL_MAX_HOLD = 15    # 청산 A의 시간상한 (2026-08-14 이전 운영값)

OHLC = ['시가', '고가', '저가', '종가']


def prep(path):
    """pkl 하나를 지표까지 계산. simulate_exit에 그대로 넘길 수 있게 OHLC 원본을 함께 반환."""
    try:
        df = pd.read_pickle(path)
    except Exception:
        return None
    need = OHLC + ['거래량', '등락률']
    if not all(c in df.columns for c in need):
        return None
    df = df[need].dropna()
    if len(df) < 60:
        return None
    df.index = pd.to_datetime(df.index)
    # 0원 행은 pkl 불량 — 남겨두면 수익률이 -100%로 계산된다
    df = df[(df[OHLC] > 0).all(axis=1)]
    if len(df) < 60:
        return None

    close = df['종가'].astype(float)
    high = df['고가'].astype(float)
    low = df['저가'].astype(float)
    tv = df['거래량'].astype(float) * close
    ma5 = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()
    ma5_chg = (ma5 / ma5.shift(1) - 1) * 100
    avg5 = tv.shift(1).rolling(5).mean()
    box = (close.shift(1).rolling(10).max() / close.shift(1).rolling(10).min() - 1) * 100

    base = ((close >= MIN_CLOSE) & (tv >= TRADING_VALUE)
            & ~((ma5 < ma20) & (ma5_chg < -3)) & ma20.notna()
            & ((box < 6) | ~((avg5 > 0) & (tv >= OVERHEAT_MULT * avg5))))

    return {
        'df': df,
        'idx': df.index,
        'op': df['시가'].astype(float).to_numpy(),
        'lo': low.to_numpy(),
        'cl': close.to_numpy(),
        'chg': df['등락률'].astype(float).to_numpy(),
        'ret5': (close / close.shift(5) - 1) * 100,
        'cpos': np.where(high > low, (close - low) / (high - low), 1.0),
        'base': base.to_numpy(),
    }


def signal_days(sig: np.ndarray) -> np.ndarray:
    """각 인덱스에서 '최근 6영업일 창(i-6..i)의 신호일 수'. 라이브 SQL의 signal_days 대응."""
    s = pd.Series(sig.astype(int))
    return s.rolling(CLUSTER_GAP + 1, min_periods=1).sum().to_numpy()


def exit_b(d, i) -> Optional[float]:
    """청산 B: 손절 -6%(1~4일차 장중 저가) 아니면 5일차 개장가 전량."""
    cl, lo, op = d['cl'], d['lo'], d['op']
    entry = cl[i]
    if i + HOLD_B >= len(cl):
        return None
    for k in range(1, HOLD_B):
        if lo[i + k] / entry - 1 <= STOP:
            return STOP * 100
    return (op[i + HOLD_B] / entry - 1) * 100


def exit_a(d, i, same_day=True) -> Optional[float]:
    """청산 A: 실제 트레일링 로직(simulate_exit)."""
    res = R.simulate_exit(d['df'][OHLC], i, d['cl'][i], TRAIL_MAX_HOLD, same_day_trigger=same_day)
    if res is None:
        return None
    # 미완결 포지션(데이터가 끝나서 잘린 것)은 최근 구간을 편향시키므로 버린다
    if res.get('exit') == 'truncated' or 'truncated' in str(res.get('exit_seq', '')):
        return None
    return res['ret_pct']


_CACHE = {}


def load_store(limit: Optional[int] = None):
    """pkl 스캔 결과를 캐시한다 — 종가위치 필터 유무로 두 번 돌 때 재스캔을 피한다."""
    if limit in _CACHE:
        return _CACHE[limit]
    mkt = load_market_map()
    files = [f for f in os.listdir(PKL_DIR) if f.endswith('.pkl')]
    if limit:
        files = files[:limit]

    print(f'1차 패스: {len(files)}종목 지표 + 시장 평균 5일수익률...', flush=True)
    store, by_market = {}, {'kospi': {}, 'kosdaq': {}}
    for n, fname in enumerate(files, 1):
        if n % 500 == 0:
            print(f'  ... {n}/{len(files)}', flush=True)
        d = prep(os.path.join(PKL_DIR, fname))
        if d is None:
            continue
        code = fname[:-4]
        store[code] = d
        m = mkt.get(code)
        if m in by_market:
            by_market[m][code] = d['ret5']
    market_ret5 = {m: pd.DataFrame(s).mean(axis=1) for m, s in by_market.items() if s}
    for m in market_ret5:
        print(f'  {m}: {len(by_market[m])}종목')
    _CACHE[limit] = (store, mkt, market_ret5)
    return _CACHE[limit]


def build(limit: Optional[int] = None, cpos_filter: bool = True):
    store, mkt, market_ret5 = load_store(limit)

    print('2차 패스: 8조합 시뮬레이션...', flush=True)
    rows = []
    for n, (code, d) in enumerate(store.items(), 1):
        if n % 500 == 0:
            print(f'  ... {n}/{len(store)}', flush=True)
        base, chg, cpos = d['base'], d['chg'], d['cpos']
        cfilter = (cpos >= CLOSE_POS_MIN) if cpos_filter else np.ones(len(cpos), bool)

        variants = {'v1': base & (chg >= 3.0)}
        m = mkt.get(code)
        if m in market_ret5:
            rel = (d['ret5'] - market_ret5[m].reindex(d['idx'])).to_numpy()
            variants['v2'] = (base & (chg >= 2.0)
                              & (rel >= REL_STRENGTH_LO) & (rel <= REL_STRENGTH_HI))

        for vname, sig in variants.items():
            if not sig.any():
                continue
            sd = signal_days(sig)
            for gname, mask in (('S', sd == 1), ('F', (sd >= 2) & (sd <= 3))):
                for i in np.flatnonzero(sig & mask & cfilter):
                    a = exit_a(d, i)
                    a_opt = exit_a(d, i, same_day=False)
                    b = exit_b(d, i)
                    if a is None and b is None:
                        continue
                    rows.append({'D': d['idx'][i], 'code': code,
                                 'group': f'{gname}{vname[-1]}',
                                 'a': a, 'a_opt': a_opt, 'b': b})
    return pd.DataFrame(rows)


LABEL = {'S1': 'S1 signal v1', 'S2': 'S2 signal v2',
         'F1': 'F1 fire2-3 v1', 'F2': 'F2 fire2-3 v2'}
EXITS = [('A 트레일링', 'a'), ('B 5일보유', 'b')]


def report(X: pd.DataFrame, title: str):
    years = sorted(X['D'].dt.year.unique())
    hdr = (f'{"조합":<26}{"건수":>8}{"기대수익%":>11}{"중앙%":>9}{"승률":>8}'
           + ''.join(f'{y:>9}' for y in years))
    print('=' * len(hdr))
    print(title)
    print('=' * len(hdr))
    print(hdr)
    print('-' * len(hdr))

    out = []
    for g in ('S1', 'S2', 'F1', 'F2'):
        for elab, col in EXITS:
            s = X[(X['group'] == g) & X[col].notna()]
            if len(s) < 200:
                out.append((float('-inf'), f'{LABEL[g]} / {elab}', len(s), None))
                continue
            exp = s[col].mean() - ROUND_TRIP
            by_y = s.groupby(s['D'].dt.year)[col].mean()
            out.append((exp, f'{LABEL[g]} / {elab}', len(s),
                        (s[col].median(), (s[col] > 0).mean() * 100,
                         [by_y.get(y, float('nan')) - ROUND_TRIP for y in years])))
    out.sort(key=lambda r: -r[0])
    for exp, name, n, extra in out:
        if extra is None:
            print(f'{name:<26}{n:>8,}   (표본부족)')
            continue
        med, win, ys = extra
        print(f'{name:<26}{n:>8,}{exp:>11.3f}{med:>9.3f}{win:>7.1f}%'
              + ''.join(f'{v:>9.3f}' for v in ys))
    print()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=None)
    args = ap.parse_args()

    X = build(limit=args.limit)
    print(f'\n총 {len(X):,}건 / {X["D"].min().date()} ~ {X["D"].max().date()}')
    print('집단별 신호 수:', X.groupby('group').size().to_dict(), '\n')

    out = report(X, '8조합 기대수익 (왕복비용 0.21% 차감, 기대수익 내림차순)')

    # 트레일링 낙관 극단 — 일봉으로는 일중 순서를 모르므로 범위로 봐야 한다
    print('=' * 72)
    print('트레일링 비관/낙관 범위 (same_day_trigger True/False)')
    print('=' * 72)
    print(f'{"조합":<20}{"비관(기본)":>12}{"낙관":>12}')
    print('-' * 72)
    for g in ('S1', 'S2', 'F1', 'F2'):
        s = X[(X['group'] == g) & X['a'].notna() & X['a_opt'].notna()]
        if len(s) < 200:
            continue
        print(f'{LABEL[g]:<20}{s["a"].mean() - ROUND_TRIP:>12.3f}'
              f'{s["a_opt"].mean() - ROUND_TRIP:>12.3f}')
    print()

    best = next((r for r in out if r[0] > float('-inf')), None)
    if best:
        print(f'★ 기대수익 1위: {best[1]}  {best[0]:+.3f}%  ({best[2]:,}건)')

    # 종가위치 필터를 뺀 경우 — fire 2-3일 규칙엔 원래 이 필터가 없었다
    print('\n' + '=' * 72)
    print('참고: 종가위치>=0.6 필터를 뺀 경우 (청산 B 기준)')
    print('=' * 72)
    Y = build(limit=args.limit, cpos_filter=False)
    for g in ('S1', 'S2', 'F1', 'F2'):
        s = Y[(Y['group'] == g) & Y['b'].notna()]
        t = X[(X['group'] == g) & X['b'].notna()]
        if len(s) < 200 or len(t) < 200:
            continue
        print(f'{LABEL[g]:<20} 필터없음 {s["b"].mean() - ROUND_TRIP:>8.3f} ({len(s):>6,}건)'
              f'   필터적용 {t["b"].mean() - ROUND_TRIP:>8.3f} ({len(t):>6,}건)')


if __name__ == '__main__':
    main()
