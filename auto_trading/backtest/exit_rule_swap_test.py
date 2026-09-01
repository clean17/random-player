# -*- coding: utf-8 -*-
"""fire(mock) 청산 규칙을 real 규칙으로 바꾸면 수익률이 달라지는가 (2026-08-26 작성).

계기: kiwoom_trailing_stop.py는 이미 이 질문을 3년/30,205건으로 검증해뒀다
(모듈 docstring 160~189행, auto_trading/backtest/exit_validation_3y.py) — 결론은
'손절-6%+5일보유(real)가 4개 연도 전부에서 트레일링(mock)을 이겼다'였다. 다만 그건
구 신호(interest, 2_finding_stocks_with_increased_volume.py 재현) 기준이다. 여기서는
같은 질문을 새 기준선인 interest_v2(상대강도 밴드, 2025 이전 데이터로만 재보정한 밴드 —
entry_relstrength_verify.py가 이미 검증한 그 밴드) 위에서, fire의 실제 mock 사이징
(슬롯20/divisor20/2,400만원/후보 20개/ratio 0.75)으로 다시 확인한다.

청산 시뮬레이터는 두 개를 그대로 재사용한다(직접 재구현하지 않음 — 재구현하면 실제
로직과 미묘하게 어긋날 위험이 있다):
  - real 규칙(손절-6%, 트레일링 없음, 5영업일 만기)  : 이 파일에서 직접 인라인(track_compare.exits()와
    동일한 8줄짜리 로직 재사용, MAX_HOLD/STOP만 5/-0.06으로 고정)
  - mock 규칙(손절-6%+트레일링+15영업일 만기)        : fire_backtest_regen.simulate_exit() —
    kiwoom_trailing_stop.py의 STOP_LOSS_RATE/TRAIL_ACTIVATE_RATE/TRAIL_GAP/MIN_PROFIT_FLOOR를
    직접 import해서 쓰므로 라이브 상수와 항상 같다. tranche(1/3씩)/재무장/보호선 로직 그대로.

⚠️ 근사: simulate_exit()은 포지션 전체의 '수량가중 평균 수익률'과 '마지막 청산일'만 반환한다
   (부분 청산 3번의 각 시점을 따로 반영하지 않음). 포트폴리오 자금흐름 시뮬레이터
   (cash_ratio_test.simulate)는 포지션 1건을 진입~단일 청산일로 다루므로, 트레일링의 중간
   부분청산으로 자금이 더 일찍 풀리는 효과는 과소평가된다 — mock 규칙에 불리한 방향의 근사다.

교차 검증(메커니즘 분리): mock 트레일링 로직 + MAX_HOLD=5, real 단순 손절 + MAX_HOLD=15도
같이 돌려서, 차이가 '보유기간'에서 오는지 '트레일링 메커니즘 자체'에서 오는지 나눠본다.

사용법:
    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe auto_trading/backtest/exit_rule_swap_test.py
    ... --limit 400   (빠른 확인)
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

from auto_trading.kiwoom_fire_strategy_mock import PKL_DIR                          # noqa: E402
from auto_trading.backtest.entry_threshold_test import (                       # noqa: E402
    TRADING_VALUE, MIN_CLOSE, CLUSTER_GAP, CLOSE_POS_MIN, OVERHEAT_MULT,
)
from auto_trading.backtest.track_compare import (                              # noqa: E402
    load_market_map, calibrate_band, V2_MIN_RATE,
)
from auto_trading.backtest import cash_ratio_test as CRT                       # noqa: E402
from auto_trading.backtest.cash_ratio_test import simulate, bootstrap          # noqa: E402
from auto_trading.backtest import fire_backtest_regen as R                     # noqa: E402

CRT.RATIOS = (0.75,)   # fire의 실제 mock CASH_DEPLOY_RATIO만 보고 싶다 — 기본 4개 값 대신 하나로 고정

SPLIT = pd.Timestamp('2025-01-01')   # track_compare.py의 walk-forward 분할과 동일
CAPITAL = 24_000_000
SLOTS = 20
DIVISOR = 20
POOL = 20
RATIO = 0.75
COST_PCT = 0.2   # 왕복비용 %


def prep_both(path):
    """prep()과 같은 지표 + 원본(한글 컬럼) 프레임을 같은 인덱스로 같이 반환.
    simulate_exit()이 한글 컬럼(시가/고가/저가/종가)을 요구해서 따로 들고 있어야 한다."""
    try:
        df = pd.read_pickle(path)
    except Exception:
        return None, None
    need = ['시가', '고가', '저가', '종가', '거래량', '등락률']
    if not all(c in df.columns for c in need):
        return None, None
    df = df[need].dropna()
    if len(df) < 60:
        return None, None
    df.index = pd.to_datetime(df.index)

    close = df['종가'].astype(float)
    high = df['고가'].astype(float)
    low = df['저가'].astype(float)
    tv = (df['거래량'].astype(float) * close)
    ma5 = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()
    ma5_chg = (ma5 / ma5.shift(1) - 1) * 100
    avg5 = tv.shift(1).rolling(5).mean()
    box = (close.shift(1).rolling(10).max() / close.shift(1).rolling(10).min() - 1) * 100

    out = pd.DataFrame({
        'close': close, 'high': high, 'low': low,
        'chg': df['등락률'].astype(float), 'tv': tv,
        'ret5': (close / close.shift(5) - 1) * 100,
        'close_pos': np.where(high > low, (close - low) / (high - low), 1.0),
        'base': (
            (close >= MIN_CLOSE) & (tv >= TRADING_VALUE)
            & ~((ma5 < ma20) & (ma5_chg < -3)) & ma20.notna()
            & ((box < 6) | ~((avg5 > 0) & (tv >= OVERHEAT_MULT * avg5)))
        ),
    })
    return out, df   # df: 한글 컬럼 원본(동일 인덱스)


def first_hits(d, cond):
    """조건을 만족하는 인덱스 중 클러스터 첫날만 남기고, 종가위치 필터까지 적용."""
    hits = np.flatnonzero(cond.to_numpy())
    if len(hits) == 0:
        return []
    firsts = [hits[0]]
    for a, b in zip(hits[:-1], hits[1:]):
        if b - a > CLUSTER_GAP:
            firsts.append(b)
    cpos = d['close_pos'].to_numpy()
    close = d['close'].to_numpy()
    return [i for i in firsts if i + 1 < len(close) and close[i] > 0 and cpos[i] >= CLOSE_POS_MIN]


def real_rule_exit(raw, i, entry, max_hold=5, stop=-0.06):
    """real 규칙: 손절(-6%, 저가 터치) 또는 max_hold일 종가 청산. track_compare.exits()와 동일 로직."""
    close = raw['종가'].to_numpy()
    low = raw['저가'].to_numpy()
    ret, hold = None, max_hold
    for k in range(1, max_hold + 1):
        j = i + k
        if j >= len(close):
            hold = k - 1
            break
        if low[j] / entry - 1 <= stop:
            ret, hold = stop * 100, k
            break
    if ret is None:
        j = min(i + hold, len(close) - 1)
        if j <= i:
            return None
        ret = (close[j] / entry - 1) * 100
    return {'ret_pct': ret, 'days': hold}


def _atr14_at(raw, i):
    """kiwoom_v8_strategy._atr14()와 동일 공식(Wilder EMA, alpha=1/14)을 진입 시점까지의
    데이터로만 계산 — 라이브(_init_pos)도 포지션 진입 시 1회만 계산해 고정하고 그 뒤로
    갱신하지 않는다."""
    h = raw['고가'].astype(float)
    l = raw['저가'].astype(float)
    pc = raw['종가'].astype(float).shift(1)
    tr = pd.concat([(h - l).abs(), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    v = tr.iloc[:i + 1].ewm(alpha=1 / 14.0, min_periods=14, adjust=False).mean().iloc[-1]
    return float(v) if np.isfinite(v) else None


def v8_rule_exit(raw, i, entry, atr_mult=3.0, trail_pct=0.05, trail_frac=0.5,
                 tp_pct=0.20, tp_frac=0.5, max_hold=10):
    """v8 청산 규칙(kiwoom_v8_exit.py 그대로): ATR(14)x3 샹들리에 손절(전량) → 트레일링
    -5%(최초수량의 절반, 1회씩 재무장 가능) → 익절+20%(나머지 절반, 1회) → 최대보유 10일(전량).
    ATR은 라이브처럼 진입 시점에 1회만 계산해 보유기간 내내 고정한다(재계산 안 함)."""
    atr = _atr14_at(raw, i)
    if atr is None or atr <= 0:
        atr = entry * 0.05   # kiwoom_v8_exit._init_pos() 폴백과 동일
    close = raw['종가'].to_numpy()
    high = raw['고가'].to_numpy()
    low = raw['저가'].to_numpy()
    open_ = raw['시가'].to_numpy()

    remaining = 1.0
    peak = entry
    trail_armed = True     # _init_pos()의 초기값 그대로(발동 즉시 무장)
    last_fire_peak = None
    tp_done = False
    realized = []          # (비중, 수익률)
    exit_j = i

    last_i = min(i + max_hold, len(close) - 1)
    for j in range(i + 1, last_i + 1):
        h, l, o = high[j], low[j], open_[j]
        if h > peak:
            peak = h

        # 1) ATR 샹들리에 손절 — 전량
        stop_px = peak - atr_mult * atr
        if l <= stop_px:
            fill_px = stop_px if o > stop_px else o
            realized.append((remaining, fill_px / entry - 1.0))
            remaining = 0.0
            exit_j = j
            break

        # 2) 트레일링 -5% — 최초수량의 절반
        trail_trigger = peak * (1.0 - trail_pct)
        if trail_armed and l <= trail_trigger and remaining > 1e-9:
            sell = min(trail_frac, remaining)
            fill_px = trail_trigger if o > trail_trigger else o
            realized.append((sell, fill_px / entry - 1.0))
            remaining -= sell
            trail_armed = False
            last_fire_peak = peak
            exit_j = j
            if remaining <= 1e-9:
                break

        # 3) 익절 +20% — 나머지 절반, 1회
        tp_trigger = entry * (1.0 + tp_pct)
        if (not tp_done) and h >= tp_trigger and remaining > 1e-9:
            sell = min(tp_frac, remaining)
            fill_px = tp_trigger if o < tp_trigger else o
            realized.append((sell, fill_px / entry - 1.0))
            remaining -= sell
            tp_done = True
            exit_j = j
            if remaining <= 1e-9:
                break

        # 재무장 — run_v8_eod(): 새 고점이 직전 트레일링 발동 고점보다 높아지면 다시 무장
        if (not trail_armed) and last_fire_peak is not None and peak > last_fire_peak:
            trail_armed = True

    if remaining > 1e-9:
        realized.append((remaining, close[last_i] / entry - 1.0))
        exit_j = last_i

    if not realized:
        return None
    w = sum(x[0] for x in realized)
    ret = sum(x[0] * x[1] for x in realized) / w if w > 0 else 0.0
    return {'ret_pct': ret * 100, 'days': max(1, exit_j - i)}


def build_entries(limit=None):
    mkt = load_market_map()
    files = [f for f in os.listdir(PKL_DIR) if f.endswith('.pkl')]
    if limit:
        files = files[:limit]

    print(f'{len(files)}종목 로드 중...', flush=True)
    store, raw_store = {}, {}
    ret5_by_market = {'kospi': {}, 'kosdaq': {}}
    for n, fname in enumerate(files, 1):
        if n % 500 == 0:
            print(f'  ... {n}/{len(files)}', flush=True)
        code = fname[:-4]
        d, raw = prep_both(os.path.join(PKL_DIR, fname))
        if d is None:
            continue
        store[code] = d
        raw_store[code] = raw
        m = mkt.get(code)
        if m in ret5_by_market:
            ret5_by_market[m][code] = d['ret5']

    market_ret5 = {}
    for m, series in ret5_by_market.items():
        if series:
            market_ret5[m] = pd.DataFrame(series).mean(axis=1)

    print('재보정 밴드 계산(2025-01-01 이전 데이터만)...', flush=True)
    band = calibrate_band(store, mkt, market_ret5, V2_MIN_RATE, SPLIT)
    print(f'  재보정 밴드: {band[0]:.2f} ~ {band[1]:.2f}%p')

    print('신호(클러스터 첫날) 추출 중...', flush=True)
    entries = []   # (code, i, entry_price, date)
    for code, d in store.items():
        m = mkt.get(code)
        if m not in market_ret5:
            continue
        rel = (d['ret5'] - market_ret5[m].reindex(d.index))
        cond = d['base'] & (d['chg'] >= V2_MIN_RATE) & (rel >= band[0]) & (rel <= band[1])
        for i in first_hits(d, cond):
            entries.append((code, i, float(d['close'].iloc[i]), d.index[i]))
    print(f'  원신호 {len(entries):,}건')
    return entries, store, raw_store


def run_variant(label, entries, raw_store, exit_fn):
    rows = []
    for code, i, entry, dt in entries:
        raw = raw_store[code]
        res = exit_fn(raw, i, entry)
        if res is None:
            continue
        net_ret = res['ret_pct'] - COST_PCT   # 왕복비용 차감(exits()/simulate_exit 둘 다 비용 미포함)
        rows.append({'code': code, 'D': dt, 'entry': entry, 'ret': net_ret,
                     'hold': max(1, int(res['days'])), 'close_pos': 1.0})
    df = pd.DataFrame(rows)
    if df.empty:
        print(f'{label}: 신호 없음')
        return None

    oos = df[df['D'] >= SPLIT].copy()
    ins = df[df['D'] < SPLIT].copy()
    print(f'\n=== {label} ===')
    print(f'  전체 {len(df):,}건 | 훈련(~2024) {len(ins):,}건 건당 {ins["ret"].mean():+.3f}%'
          f' | 시험(2025~) {len(oos):,}건 건당 {oos["ret"].mean():+.3f}% 승률 {(oos["ret"]>0).mean()*100:.1f}%')

    if len(oos) < 30:
        print('  시험 구간 표본 부족 — 포트폴리오 생략')
        return oos

    bootstrap(oos, CAPITAL, SLOTS, DIVISOR, POOL, n_iter=30)
    return oos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=None)
    args = ap.parse_args()

    entries, store, raw_store = build_entries(args.limit)

    run_variant('REAL 규칙 (손절-6% / 트레일링 없음 / 5영업일)', entries, raw_store,
               lambda raw, i, entry: real_rule_exit(raw, i, entry, max_hold=5, stop=-0.06))

    run_variant('MOCK 규칙 (손절-6% / 트레일링 +7%~5%p~3%바닥 / 15영업일, 라이브 상수 그대로)',
               entries, raw_store,
               lambda raw, i, entry: R.simulate_exit(raw, i, entry, max_hold=15))

    # 메커니즘 분리: 보유기간만 바꿔서 어느 쪽이 효과를 지배하는지 확인
    run_variant('교차1: REAL 손절규칙 + 15영업일(mock 보유기간만 이식)', entries, raw_store,
               lambda raw, i, entry: real_rule_exit(raw, i, entry, max_hold=15, stop=-0.06))

    run_variant('교차2: MOCK 트레일링 + 5영업일(real 보유기간만 이식)', entries, raw_store,
               lambda raw, i, entry: R.simulate_exit(raw, i, entry, max_hold=5))

    # 2026-08-26: '교차1'(REAL 손절+15일, 트레일링 없음)이 실제로 라이브에 반영됐다
    # (kiwoom_trailing_stop.py TRAILING_ENABLED=False, MAX_HOLD_DAYS=15로 통일).
    # v8 자체 청산 공식(ATR샹들리에+트레일링-5%+익절+20%+10일, kiwoom_v8_exit.py)을 fire
    # 신호에 얹으면 이 새 라이브 설정보다 더 나은지 확인.
    run_variant('v8 공식 (ATR3샹들리에+트레일링-5%/절반+익절+20%/절반+10영업일)', entries, raw_store,
               lambda raw, i, entry: v8_rule_exit(raw, i, entry))

    print('\n(모든 수치는 왕복비용 0.2% 차감 후, 시험구간(2025-01-01~)만 헤드라인.)')


if __name__ == '__main__':
    main()
