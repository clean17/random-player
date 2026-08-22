# -*- coding: utf-8 -*-
"""fire 후보 트랙 비교: interest vs interest_v2 (2026-08-18 작성).

질문: 지금 fire 전략은 target='interest'만 쓰는데, interest_v2(상대강도 밴드 추가판)로
바꾸면 더 나은가?

★ DB로는 답할 수 없다 — interest_v2는 2026-08-11 도입이라 이력이 168건/5거래일뿐이다.
  그래서 두 트랙의 스캐너 로직을 pkl에서 3년치 재현해 같은 조건으로 비교한다.

━━━ 두 트랙의 차이 (AutoSales.py/job/) ━━━
  interest    ← 2_finding_stocks_with_increased_volume.py : 공통 게이트 + 등락률 >= 3%
  interest_v2 ← 2_finding_stocks_advanced.py              : 공통 게이트 + 등락률 >= 2%
                                                            + 상대강도 밴드 2.8 ~ 7.1%p
  상대강도 = 종목 5일수익률 - 같은 시장(코스피/코스닥) 전 종목 5일수익률 평균.
  시장 평균은 매일 새로 계산되고 밴드 경계값만 고정이다(하드코딩).

━━━ 공통 게이트 (양 트랙 동일) ━━━
  종가 >= 700원 / 오늘 거래대금 >= 20억 / NOT(MA5<MA20 AND MA5 일간변화율 < -3%)
  / 박스권(10일 변동폭<6%) OR 과열아님(오늘거래대금 < 5x5일평균)

━━━ downstream (라이브 fire 규칙과 동일) ━━━
  signal_days=1 상당(6영업일 창의 첫 신호일만) + 종가위치>=0.6 + 손절-6%/5영업일, 왕복비용 0.2%

⚠️ 시가총액 700억·평균거래대금 40억 필터와 reserved 교집합은 재현하지 못한다(pkl에 시총 없음).
   두 트랙에 동일하게 빠지므로 상대 비교는 성립하지만 절대 수익률은 실제와 다르다.
   생존편향(상장폐지 종목이 pkl에 없음)도 포함한다.

━━━ 결과 (2026-08-18, pkl 2,858종목 / 약 3년) ━━━

  A. 신호 품질 (건당, 왕복비용 0.2% 차감)
     interest      31,499건  일 38.2건  -0.013%  승률 38.0%  | 2024 -0.167 / 2025 +0.313 / 2026 -0.065
     interest_v2   16,798건  일 20.4건  +0.174%  승률 40.0%  | 2024 -0.177 / 2025 +0.517 / 2026 +0.522

     v2가 건당 +0.19%p 앞선다. 겹치는 신호는 v2의 44.5%뿐이고 v2 전용이 9,322건이라,
     interest의 부분집합이 아니라 다른 종목·다른 날을 잡는다.

  B. Walk-forward (과적합 검증) — 밴드는 2026-08 시점 1년 데이터로 뽑은 값이라
     2025~2026이 in-sample이다. 그래서 2025-01-01 이전만으로 밴드를 재보정해 검증했다.
     재보정 밴드 2.49~5.92%p (현행 하드코딩 2.8~7.1과 큰 차이 없음 = 밴드가 민감하지 않다)

                    interest   v2(현행밴드)  v2(재보정밴드)
       훈련(~2024)   -0.175      -0.146       -0.134
       시험(2025~)   +0.163      +0.519       +0.457

     ★ 2025년 이후를 전혀 보지 않고 뽑은 밴드도 시험구간에서 interest를 +0.29%p 앞선다.
       3년 전체의 우위가 밴드 과적합만은 아니라는 뜻. 다만 하락 레짐(~2024)에서는
       두 트랙 모두 마이너스이고 차이도 노이즈 수준이라, v2의 강점은 '상승 레짐에서
       더 잘 번다'이지 '하락을 방어한다'가 아니다.

  C. 포트폴리오 (부트스트랩 25회, 슬롯5/divisor5/후보상위7, --bootstrap 25로 재현)
     ratio 0.70(구 분모) 기준 총수익 평균: interest -18.8% / v2 +14.0%
     ⚠️ 이 절대 수치는 신뢰하지 말 것. 시총 700억 필터를 재현하지 못해 소형주가 대량 유입되고,
        2024년(양 트랙 모두 마이너스)이 포함돼 있다. cash_ratio_test.py가 DB 신호로 낸
        +17.1%와는 모집단이 달라 비교 불가다. 여기서 읽을 것은 '두 트랙의 상대 격차'뿐이다.
     노출-성과 단조 역상관은 두 트랙 모두에서 재현된다(ratio를 올릴수록 나빠짐).

⚠️ 실전 전환 시 검토할 것: v2는 신호량이 절반이다(일 20.4 vs 38.2건). reserved 교집합까지
   걸면 후보가 하루 3~4종목으로 줄 수 있고, 그러면 2026-08-14처럼 한도를 못 쓰는 문제가
   다시 생긴다. 화면에서 reserved를 고르는 모집단도 어느 트랙인지 함께 정해야 한다.

사용법:
    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe auto_trading/backtest/track_compare.py
    ... --bootstrap 25      (포트폴리오 부트스트랩까지)
    ... --walkforward       (밴드 재보정 과적합 검증)
    ... --limit 300         (빠른 확인)
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

from auto_trading.kiwoom_fire_strategy import PKL_DIR                    # noqa: E402
from auto_trading.backtest.entry_threshold_test import (                 # noqa: E402
    TRADING_VALUE, MIN_CLOSE, CLUSTER_GAP, CLOSE_POS_MIN,
    STOP, MAX_HOLD, COST, OVERHEAT_MULT,
)
from auto_trading.backtest.cash_ratio_test import simulate, bootstrap    # noqa: E402

# 2_finding_stocks_advanced.py:90-91과 같게 유지할 것
REL_STRENGTH_LO = 2.8
REL_STRENGTH_HI = 7.1
INTEREST_MIN_RATE = 3.0    # 2_finding_stocks_with_increased_volume.py
V2_MIN_RATE = 2.0          # 2_finding_stocks_advanced.py


def load_market_map() -> Dict[str, str]:
    """stock_code -> 'kospi' | 'kosdaq'. pkl에 시장 구분이 없어 DB에서 가져온다."""
    from config.db_connect import db_pool
    with db_pool.connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT stock_code, stock_market FROM stocks WHERE stock_market IS NOT NULL")
        return {str(c).zfill(6): m for c, m in cur.fetchall()}


def prep(path: str) -> Optional[pd.DataFrame]:
    """pkl 하나를 지표까지 계산해 반환. 게이트 판정에 필요한 컬럼만 남긴다."""
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
        # 5일 수익률 — 상대강도의 재료
        'ret5': (close / close.shift(5) - 1) * 100,
        'close_pos': np.where(high > low, (close - low) / (high - low), 1.0),
        'base': (
            (close >= MIN_CLOSE) & (tv >= TRADING_VALUE)
            & ~((ma5 < ma20) & (ma5_chg < -3)) & ma20.notna()
            & ((box < 6) | ~((avg5 > 0) & (tv >= OVERHEAT_MULT * avg5)))
        ),
    })
    return out


def exits(d: pd.DataFrame, hits: np.ndarray) -> List[Dict]:
    """신호 인덱스 배열 → 클러스터 첫날만 남기고 종가위치 필터 + 청산 계산."""
    if len(hits) == 0:
        return []
    firsts = [hits[0]]
    for a, b in zip(hits[:-1], hits[1:]):
        if b - a > CLUSTER_GAP:
            firsts.append(b)

    close = d['close'].to_numpy()
    low = d['low'].to_numpy()
    cpos = d['close_pos'].to_numpy()
    chg = d['chg'].to_numpy()
    idx = d.index

    recs = []
    for i in firsts:
        if i + 1 >= len(close) or close[i] <= 0 or cpos[i] < CLOSE_POS_MIN:
            continue
        entry = close[i]
        ret, hold = None, MAX_HOLD
        for k in range(1, MAX_HOLD + 1):
            j = i + k
            if j >= len(close):
                hold = k - 1
                break
            if low[j] / entry - 1 <= STOP:
                ret, hold = STOP * 100, k
                break
        if ret is None:
            j = min(i + hold, len(close) - 1)
            if j <= i:
                continue
            ret = (close[j] / entry - 1) * 100
        recs.append({'D': idx[i], 'entry': entry, 'close_pos': cpos[i],
                     'chg': chg[i], 'ret': ret, 'hold': hold})
    return recs


def make_track(store, mkt, market_ret5, min_rate, band=None):
    """게이트 + (선택) 상대강도 밴드로 트랙 하나를 생성.

    밴드는 클러스터링 '전에' 적용해야 한다 — 밴드가 어떤 날을 신호로 인정하느냐가
    첫 신호일 자체를 바꾸기 때문. 그래서 밴드를 바꿀 때마다 exits()를 다시 돌린다.
    """
    recs = []
    for code, d in store.items():
        base = d['base'].to_numpy()
        chg = d['chg'].to_numpy()
        cond = base & (chg >= min_rate)
        rel = None
        if band is not None:
            m = mkt.get(code)
            if m not in market_ret5:
                continue
            rel = (d['ret5'] - market_ret5[m].reindex(d.index)).to_numpy()
            cond = cond & (rel >= band[0]) & (rel <= band[1])
        for r in exits(d, np.flatnonzero(cond)):
            r['code'] = code
            recs.append(r)
    return pd.DataFrame(recs)


def calibrate_band(store, mkt, market_ret5, min_rate, upto, lo_pct=40, hi_pct=60):
    """훈련 구간의 상대강도 분포에서 lo~hi 백분위를 밴드로 뽑는다.

    2_finding_stocks_advanced.py가 2.8~7.1을 얻은 방법(1년 재현 데이터의 40~60%tile)을
    임의 구간에 대해 재현한 것. upto 이전 데이터만 본다.
    """
    vals = []
    for code, d in store.items():
        m = mkt.get(code)
        if m not in market_ret5:
            continue
        rel = d['ret5'] - market_ret5[m].reindex(d.index)
        sel = d['base'] & (d['chg'] >= min_rate) & (d.index < upto) & rel.notna()
        vals.append(rel[sel])
    if not vals:
        return None
    allv = pd.concat(vals)
    return float(np.percentile(allv, lo_pct)), float(np.percentile(allv, hi_pct))


def build(limit: Optional[int] = None):
    mkt = load_market_map()
    files = [f for f in os.listdir(PKL_DIR) if f.endswith('.pkl')]
    if limit:
        files = files[:limit]

    print(f'1차 패스: {len(files)}종목 지표 계산 + 시장 평균 5일수익률 집계...', flush=True)
    store = {}
    ret5_by_market = {'kospi': {}, 'kosdaq': {}}   # market -> {code: Series}
    for n, fname in enumerate(files, 1):
        if n % 500 == 0:
            print(f'  ... {n}/{len(files)}', flush=True)
        code = fname[:-4]
        d = prep(os.path.join(PKL_DIR, fname))
        if d is None:
            continue
        store[code] = d
        m = mkt.get(code)
        if m in ret5_by_market:
            ret5_by_market[m][code] = d['ret5']

    # 날짜별 시장 평균 5일수익률 (스캐너의 market_ret5와 동일하게 동일가중 평균)
    market_ret5 = {}
    for m, series in ret5_by_market.items():
        if series:
            market_ret5[m] = pd.DataFrame(series).mean(axis=1)
            print(f'  {m}: {len(series)}종목')

    print('2차 패스: 트랙별 신호 생성...', flush=True)
    tracks = {
        'interest': make_track(store, mkt, market_ret5, INTEREST_MIN_RATE),
        'v2': make_track(store, mkt, market_ret5, V2_MIN_RATE,
                         (REL_STRENGTH_LO, REL_STRENGTH_HI)),
    }
    return tracks, store, mkt, market_ret5


def net(ret: pd.Series) -> float:
    return float(ret.mean()) - COST * 100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--bootstrap', type=int, default=0)
    ap.add_argument('--capital', type=int, default=1_990_000)
    ap.add_argument('--walkforward', action='store_true',
                    help='밴드를 훈련구간에서 재보정해 시험구간에 적용 (과적합 검증)')
    ap.add_argument('--split', type=str, default='2025-01-01')
    args = ap.parse_args()

    tracks, store, mkt, market_ret5 = build(limit=args.limit)
    years = [2024, 2025, 2026]

    hdr = (f'{"트랙":<12}{"건수":>9}{"일평균":>8}{"비용후%":>10}{"중앙%":>9}{"승률":>8}'
           f'{"보유일":>8}' + ''.join(f'{y:>10}' for y in years))
    print('\n' + '=' * len(hdr))
    print('A. 신호 품질 — 건당 (첫신호일 + 종가위치>=0.6 + 손절-6%/5일, 왕복비용 0.2% 차감)')
    print('=' * len(hdr))
    print(hdr)
    print('-' * len(hdr))
    for name, X in (('interest', tracks['interest']), ('interest_v2', tracks['v2'])):
        if X.empty:
            print(f'{name:<12}   (신호 없음)')
            continue
        days = X['D'].nunique()
        print(f'{name:<12}{len(X):>9,}{len(X) / max(1, days):>8.1f}{net(X["ret"]):>10.3f}'
              f'{X["ret"].median():>9.3f}{(X["ret"] > 0).mean() * 100:>7.1f}%'
              f'{X["hold"].mean():>8.2f}', end='')
        for y in years:
            s = X[X['D'].dt.year == y]
            print(f'{net(s["ret"]) if len(s) > 100 else float("nan"):>10.3f}', end='')
        print()
    print()

    # 두 트랙이 같은 신호를 얼마나 공유하는지 — v2가 '다른 종목'을 잡는지 '같은 종목을
    # 다른 날' 잡는지 구분해야 결과를 해석할 수 있다.
    a = set(zip(tracks['interest']['code'], tracks['interest']['D']))
    b = set(zip(tracks['v2']['code'], tracks['v2']['D']))
    print(f'중복(같은 종목·같은 날): {len(a & b):,}건 '
          f'— interest의 {len(a & b) / max(1, len(a)):.1%}, v2의 {len(a & b) / max(1, len(b)):.1%}')
    print(f'v2 전용 {len(b - a):,}건 / interest 전용 {len(a - b):,}건\n')

    if args.walkforward:
        split = pd.Timestamp(args.split)
        band = calibrate_band(store, mkt, market_ret5, V2_MIN_RATE, upto=split)
        print('=' * len(hdr))
        print(f'B. Walk-forward — 밴드를 {split.date()} 이전 데이터의 40~60%tile로 재보정')
        print('=' * len(hdr))
        print(f'훈련구간 재보정 밴드: {band[0]:.2f} ~ {band[1]:.2f}%p '
              f'(현행 하드코딩 {REL_STRENGTH_LO} ~ {REL_STRENGTH_HI})')
        wf = make_track(store, mkt, market_ret5, V2_MIN_RATE, band)
        print()
        print(f'{"구간":<10}{"트랙":<22}{"건수":>9}{"비용후%":>10}{"승률":>8}')
        print('-' * 60)
        for lab, mask in (('훈련(IS)', lambda d: d['D'] < split),
                          ('시험(OOS)', lambda d: d['D'] >= split)):
            for name, X in (('interest', tracks['interest']),
                            ('v2 (현행밴드 2.8~7.1)', tracks['v2']),
                            ('v2 (재보정밴드)', wf)):
                s = X[mask(X)]
                if len(s) < 100:
                    print(f'{lab:<10}{name:<22}{len(s):>9,}   (표본부족)')
                    continue
                print(f'{lab:<10}{name:<22}{len(s):>9,}{net(s["ret"]):>10.3f}'
                      f'{(s["ret"] > 0).mean() * 100:>7.1f}%')
            print('-' * 60)
        print('\n※ 시험구간에서 v2가 interest를 못 이기면, 3년 전체의 우위는 밴드가 그 기간에\n'
              '  맞춰진 결과(과적합)로 봐야 한다.\n')

    if args.bootstrap:
        for name, X in (('interest', tracks['interest']), ('interest_v2', tracks['v2'])):
            if len(X) < 500:
                print(f'[{name}] 표본 부족으로 포트폴리오 시뮬 생략')
                continue
            print(f'\n########## 포트폴리오: {name} ##########')
            bootstrap(X, args.capital, slots=5, divisor=5, pool=7, n_iter=args.bootstrap)


if __name__ == '__main__':
    main()
