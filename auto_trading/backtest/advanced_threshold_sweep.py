# -*- coding: utf-8 -*-
"""2_finding_stocks_advanced.py의 TODAY_RATE_OF_INCREASE(당일 등락률 하한) 검증 (2026-08-14 작성).

계기: 임계값을 3 → 2로 낮췄는데 그게 나은지, 아예 없애면(0 또는 하한 없음) 어떤지 확인 요청.

━━━ 방법 ━━━
DB(interest_stocks)는 '이미 그 임계값을 통과한 신호'만 들고 있어서 낮춘 경우를 평가할 수 없다.
그래서 2_finding_stocks_advanced.py의 선정 조건을 pkl 일봉으로 재현해 임계값만 바꿔가며
신호를 새로 만들고, 각 신호에 현재 청산 규칙(fire_backtest_regen.simulate_exit)을 적용한다.

재현한 조건 (스크립트와 동일 순서):
    1. 금일 거래대금 >= TRADING_VALUE(20억)
    2. MA5 < MA20 이면서 MA5 하락률 < -3% 이면 제외
    3. 종가 >= 700원
    4. 당일 등락률 >= TODAY_RATE_OF_INCREASE      ← 이 값을 스윕한다
    5. 상대강도 밴드: REL_STRENGTH_LO <= (자기 5일수익률 - 시장 5일수익률) <= REL_STRENGTH_HI
    6. (박스권 6% 이내) 또는 (거래대금 과열 아님: 코스피 6배/코스닥 5배 미만) 중 하나는 성립

⚠️ 재현하지 못한 조건: 시가총액 700억 이상.
   시총은 Toss 실시간 조회라 과거 시점 값을 알 수 없다. 모든 임계값에 동일하게 빠지므로
   '임계값 간 상대비교'는 유효하지만, 절대 수익률은 실제와 다르다.

사용법:
    venv/Scripts/python.exe auto_trading/backtest/advanced_threshold_sweep.py
    venv/Scripts/python.exe auto_trading/backtest/advanced_threshold_sweep.py --start 2025-09-01
"""
import argparse
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from auto_trading.backtest.fire_backtest_regen import load_ohlc, simulate_exit  # noqa: E402
from auto_trading.kiwoom_fire_strategy import PKL_DIR  # noqa: E402

# 2_finding_stocks_advanced.py와 같은 값으로 유지할 것
TRADING_VALUE = 2_000_000_000
REL_STRENGTH_LO = 2.8
REL_STRENGTH_HI = 7.1
MIN_CLOSE = 700
MAX_HOLD = 15


def safe_rate(a, b):
    return (a / b - 1.0) * 100 if b else 0.0


def build_signals(start, end):
    """전 종목·전 거래일에 대해 조건별 통과 여부와 그날 등락률을 미리 계산해둔다."""
    from app.repository.stocks.stocks import get_stock_list
    market_of = {s['stock_code']: s.get('stock_market') for s in get_stock_list('kor')}

    frames = {}
    for code, mkt in market_of.items():
        if mkt not in ('kospi', 'kosdaq'):
            continue
        # load_ohlc()는 시/고/저/종만 남기므로(simulate_exit용) 거래량·등락률은 원본에서 따로 읽는다.
        ohlc = load_ohlc(code)
        if ohlc is None or len(ohlc) < 30:
            continue
        try:
            raw = pd.read_pickle(os.path.join(PKL_DIR, f'{code}.pkl'))
            raw.index = pd.to_datetime(raw.index)
        except Exception:
            continue
        if '거래량' not in raw.columns:
            continue
        d = ohlc.copy()
        d['거래량'] = raw['거래량'].reindex(d.index)
        if '등락률' in raw.columns:
            d['등락률'] = raw['등락률'].reindex(d.index)
        d['MA5'] = d['종가'].rolling(5).mean()
        d['MA20'] = d['종가'].rolling(20).mean()
        d['tv'] = d['거래량'] * d['종가']
        d['ret5'] = d['종가'].pct_change(5) * 100
        frames[code] = (d, mkt)

    # 시장 평균 5일수익률(일자별) — 상대강도 기준선
    mkt_sum = defaultdict(lambda: defaultdict(float))
    mkt_cnt = defaultdict(lambda: defaultdict(int))
    for code, (d, mkt) in frames.items():
        for ts, v in d['ret5'].dropna().items():
            if np.isfinite(v):
                mkt_sum[mkt][ts] += v
                mkt_cnt[mkt][ts] += 1

    rows = []
    for code, (d, mkt) in frames.items():
        idx = d.index
        for i in range(21, len(d) - 1):
            ts = idx[i]
            if not (start <= ts <= end):
                continue
            tv = float(d['tv'].iloc[i])
            if tv < TRADING_VALUE:
                continue
            ma5, ma5_prev, ma20 = (float(d['MA5'].iloc[i]), float(d['MA5'].iloc[i - 1]),
                                   float(d['MA20'].iloc[i]))
            if not np.isfinite(ma5) or not np.isfinite(ma20):
                continue
            if ma5 < ma20 and safe_rate(ma5, ma5_prev) < -3:
                continue
            close = float(d['종가'].iloc[i])
            if close < MIN_CLOSE:
                continue

            own5 = float(d['ret5'].iloc[i])
            n = mkt_cnt[mkt].get(ts, 0)
            if not np.isfinite(own5) or n == 0:
                continue
            rel = own5 - (mkt_sum[mkt][ts] / n)
            if not (REL_STRENGTH_LO <= rel <= REL_STRENGTH_HI):
                continue

            # 박스권 / 과열 조건 (둘 다 실패하면 제외)
            box = d['종가'].iloc[i - 10:i].values
            passed_box = safe_rate(box.max(), box.min()) < 6
            avg5 = d['tv'].iloc[i - 5:i].mean()
            if not np.isfinite(avg5) or avg5 <= 0:
                avg5 = d['tv'].iloc[i - 20:i].mean()
            passed_heat = True
            if np.isfinite(avg5) and avg5 > 0:
                mult = 6 if mkt == 'kospi' else 5
                passed_heat = tv < mult * avg5
            if not passed_box and not passed_heat:
                continue

            chg = float(d['등락률'].iloc[i]) if '등락률' in d.columns else safe_rate(
                close, float(d['종가'].iloc[i - 1]))
            rows.append({'code': code, 'i': i, 'D': ts, 'chg': chg, 'close': close})

    return rows, frames


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', default='2025-09-01')
    ap.add_argument('--end', default='2026-08-12')
    args = ap.parse_args()
    start, end = pd.Timestamp(args.start), pd.Timestamp(args.end)

    print(f'신호 재현 중... ({args.start} ~ {args.end})')
    rows, frames = build_signals(start, end)
    print(f'등락률 하한 적용 전 후보: {len(rows):,}건\n')

    # 각 후보의 청산 결과를 한 번만 계산해두고, 임계값별로 필터링만 다르게 한다.
    for r in rows:
        d, _ = frames[r['code']]
        res = simulate_exit(d, r['i'], r['close'], MAX_HOLD)
        r['ret'] = res['ret_pct'] if res else None
    ok = [r for r in rows if r['ret'] is not None]
    print(f'청산 시뮬레이션 성공: {len(ok):,}건\n')

    df = pd.DataFrame(ok)
    split = pd.Timestamp('2026-04-30')

    print('=' * 88)
    print('당일 등락률 하한(TODAY_RATE_OF_INCREASE)별 성과')
    print('=' * 88)
    print(f'{"하한":<8}{"건수":>8}{"일평균":>8}{"평균%":>9}{"중앙%":>9}{"승률":>8}{"train%":>9}{"test%":>9}')
    print('-' * 88)
    ndays = df['D'].dt.date.nunique()
    for th in (None, 0, 1, 2, 3, 4, 5):
        sub = df if th is None else df[df['chg'] >= th]
        if len(sub) == 0:
            continue
        tr = sub[sub['D'] <= split]['ret']
        te = sub[sub['D'] > split]['ret']
        label = '없음' if th is None else f'{th}%'
        mark = '  <= 현재' if th == 2 else ('  (이전)' if th == 3 else '')
        print(f'{label:<8}{len(sub):>8,}{len(sub) / ndays:>8.1f}{sub["ret"].mean():>9.3f}'
              f'{sub["ret"].median():>9.3f}{(sub["ret"] > 0).mean() * 100:>7.1f}%'
              f'{tr.mean() if len(tr) else float("nan"):>9.3f}'
              f'{te.mean() if len(te) else float("nan"):>9.3f}{mark}')

    print()
    print('=' * 88)
    print('등락률 구간별 (하한을 낮출 때 새로 들어오는 구간이 실제로 어떤지)')
    print('=' * 88)
    print(f'{"구간":<14}{"건수":>8}{"평균%":>9}{"중앙%":>9}{"승률":>8}{"train%":>9}{"test%":>9}')
    print('-' * 88)
    bands = [(-100, 0), (0, 1), (1, 2), (2, 3), (3, 5), (5, 8), (8, 12), (12, 100)]
    for lo, hi in bands:
        sub = df[(df['chg'] >= lo) & (df['chg'] < hi)]
        if len(sub) == 0:
            continue
        tr = sub[sub['D'] <= split]['ret']
        te = sub[sub['D'] > split]['ret']
        print(f'{f"{lo}~{hi}%":<14}{len(sub):>8,}{sub["ret"].mean():>9.3f}{sub["ret"].median():>9.3f}'
              f'{(sub["ret"] > 0).mean() * 100:>7.1f}%'
              f'{tr.mean() if len(tr) else float("nan"):>9.3f}'
              f'{te.mean() if len(te) else float("nan"):>9.3f}')


if __name__ == '__main__':
    main()
