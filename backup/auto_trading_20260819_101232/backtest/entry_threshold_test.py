# -*- coding: utf-8 -*-
"""스캐너 등락률 문턱(TODAY_RATE_OF_INCREASE) 3% → 2% 검증 (2026-08-18 작성).

계기: AutoSales.py의 2_finding_stocks_with_increased_volume.py 문턱을 3→2로 내렸는데
근거가 없었다. "2~3% 구간 종목이 3%+ 구간보다 나은가, 못한가"를 측정한다.

★ DB로는 답할 수 없다 — interest_stocks의 과거 신호는 전부 문턱 3%에서 생성돼
  2~3% 구간 표본이 21,383건 중 20건뿐이다. 그래서 pkl에서 스캐너를 재현한다.

━━━ 재현하는 스캐너 게이트 (2_finding_stocks_with_increased_volume.py 기준) ━━━
  종가 >= 700원
  오늘 거래대금(거래량×종가) >= 20억
  등락률 >= 문턱                                   ← 이 값을 3 vs 2로 바꿔가며 비교
  NOT (MA5 < MA20 AND MA5 일간변화율 < -3%)
  박스권(10일 변동폭<6%) OR 과열아님(오늘거래대금 < 5×5일평균)   ← 둘 다 실패해야 제외

⚠️ 시가총액 700억 필터는 재현하지 못한다 — pkl에 시총이 없다. 두 문턱에 동일하게
   빠지므로 '3% vs 2%' 비교 자체는 성립하지만, 절대 수익률은 실제와 다를 수 있다.
⚠️ 과열 배수는 코스피 6배/코스닥 5배인데 시장 구분이 pkl에 없어 5배로 통일했다
   (보수적 방향 — 코스피 종목을 실제보다 조금 더 걸러낸다).

━━━ 문턱 아래 downstream (auto_trading 실제 진입/청산 규칙) ━━━
  첫 신호일만 (6영업일 이상 끊기면 다른 묶음 — CLUSTER_GAP)
  종가위치 >= 0.6 (CLOSE_POS_MIN)
  청산: 손절 -6%(장중 저가 터치) 또는 5영업일 보유, 왕복비용 0.2%

★ 문턱은 클러스터링 자체를 바꾼다. 5% 급등일 앞에 2.5% 날이 있었다면, 문턱 2%에서는
  '첫 신호일'이 그 2.5% 날로 앞당겨진다. 그래서 3%에서도 잡혔을 종목의 진입일까지
  달라진다 — 단순히 '2~3% 구간이 추가된다'가 아니다. 두 문턱을 각각 전체 파이프라인으로
  돌려 비교하는 이유다.

━━━ 결과 (2026-08-18, pkl 2,858종목 전량 / 약 3년) ━━━

  A. 문턱 전체 (비용후 %, 왕복 0.2% 차감)
     문턱 3%  31,499건  -0.013  승률 38.0%   2024 -0.167 / 2025 +0.313 / 2026 -0.063
     문턱 2%  30,693건  -0.032  승률 38.4%   2024 -0.234 / 2025 +0.300 / 2026 -0.095

  → 2%가 개선이 아니다. 둘 다 사실상 0이고 차이도 노이즈지만 방향은 소폭 악화다.

  B. 신호가 늘지 않고 줄어든다 (31,499 → 30,693, -2.6%)
     라이브 fire SQL이 `AND b.signal_days = 1`(6일 창에 신호일 정확히 1일)을 요구하기
     때문이다. 문턱을 내리면 신호일 수가 늘어 signal_days가 2~3이 되고, 그러면 오히려
     조건에서 탈락한다. '문턱을 낮추면 후보가 늘어난다'는 직관과 반대다.

  C. 실제 효과는 '2~3% 신규 편입'이 아니라 '진입일 앞당김'이다
     문턱3의 3%+   31,499건  -0.013
     문턱2의 3%+   23,687건  -0.017    ← 7,812건이 아래로 이동
     문턱2의 2~3%   7,006건  -0.082    ← 앞당겨진 진입이 더 나쁘다
     5% 급등일 앞에 2.5% 날이 있으면 첫 신호일이 그 2.5% 날로 당겨지고, 6% 급등일은
     signal_days=2가 되어 막힌다. 좋은 날을 놓치고 약한 날에 들어가는 교환이다.

  D. 등락률 구간별 (문턱 2% 파이프라인)
     2~3%   7,006건  -0.082   승률 41.6%   2024 -0.392 / 2025 +0.185 / 2026 +0.700
     3~5%  10,007건  -0.032   승률 40.6%
     5~8%   7,713건  -0.035   승률 38.7%
     8~12%  3,243건  +0.295   승률 35.2%
     12~20% 1,518건  -0.765   승률 26.9%
     20%+   1,206건  +0.329   승률 22.8%
     단조성이 없다 — 8~12%와 20%+만 플러스인데 그 사이 12~20%가 -0.765로 뒤집힌다.
     등락률 자체가 안정적인 예측변수가 아니라는 뜻이라, 문턱 위치로 성과를 끌어올리려는
     시도는 어느 방향이든 근거가 약하다.

⚠️ 재현 한계: 시가총액 700억·평균거래대금 40억 필터와 reserved 교집합은 재현하지 못한다.
   절대 수익률은 실제와 다르다. 다만 두 문턱에 동일하게 빠지므로 '3% vs 2%' 비교는 성립한다.
   생존편향(상장폐지 종목이 pkl에 없음)도 포함한다.

사용법:
    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe auto_trading/backtest/entry_threshold_test.py
    ... --years 2024,2025,2026     (연도별 분할)
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

from auto_trading.kiwoom_fire_strategy import PKL_DIR   # noqa: E402

TRADING_VALUE = 2_000_000_000   # 거래대금 20억
MIN_CLOSE = 700
CLUSTER_GAP = 6                 # 영업일 기준 신호 묶음 간격
CLOSE_POS_MIN = 0.6
STOP = -0.06
MAX_HOLD = 5
COST = 0.002
OVERHEAT_MULT = 5               # 코스닥 기준 (코스피는 6배지만 시장 구분이 pkl에 없음)


def scan_one(path: str, thresholds: List[float]) -> Dict[float, List[Dict]]:
    """pkl 하나에서 문턱별 신호를 뽑아 청산까지 계산. {문턱: [레코드]} 반환."""
    try:
        df = pd.read_pickle(path)
    except Exception:
        return {}
    need = ['시가', '고가', '저가', '종가', '거래량', '등락률']
    if not all(c in df.columns for c in need):
        return {}
    df = df[need].dropna()
    if len(df) < 60:
        return {}
    df.index = pd.to_datetime(df.index)

    close = df['종가'].to_numpy(dtype=float)
    high = df['고가'].to_numpy(dtype=float)
    low = df['저가'].to_numpy(dtype=float)
    chg = df['등락률'].to_numpy(dtype=float)
    tv = (df['거래량'] * df['종가']).to_numpy(dtype=float)

    ma5 = pd.Series(close).rolling(5).mean().to_numpy()
    ma20 = pd.Series(close).rolling(20).mean().to_numpy()
    # MA5 일간 변화율(%)
    with np.errstate(divide='ignore', invalid='ignore'):
        ma5_chg = np.r_[np.nan, (ma5[1:] / ma5[:-1] - 1) * 100]
        # 5일 평균 거래대금(오늘 제외)
        avg5 = pd.Series(tv).shift(1).rolling(5).mean().to_numpy()
        # 10일 박스권 변동폭(어제까지)
        roll_max = pd.Series(close).shift(1).rolling(10).max().to_numpy()
        roll_min = pd.Series(close).shift(1).rolling(10).min().to_numpy()
        box_pct = (roll_max / roll_min - 1) * 100
        close_pos = np.where(high > low, (close - low) / (high - low), 1.0)

    # 문턱과 무관한 공통 게이트
    base = (
        (close >= MIN_CLOSE)
        & (tv >= TRADING_VALUE)
        & ~((ma5 < ma20) & (ma5_chg < -3))
        & np.isfinite(ma20)
    )
    # 박스권 OR 과열아님 — 둘 다 실패할 때만 제외
    cond_box = np.isfinite(box_pct) & (box_pct < 6)
    cond_not_overheat = ~(np.isfinite(avg5) & (avg5 > 0) & (tv >= OVERHEAT_MULT * avg5))
    base = base & (cond_box | cond_not_overheat)

    idx = df.index
    out = {}
    for t in thresholds:
        hits = np.flatnonzero(base & (chg >= t))
        if len(hits) == 0:
            out[t] = []
            continue

        # 클러스터링: 직전 신호와 6영업일 이상 벌어지면 새 묶음 → 그 첫날만 진입
        firsts = [hits[0]]
        for a, b in zip(hits[:-1], hits[1:]):
            if b - a > CLUSTER_GAP:
                firsts.append(b)

        recs = []
        for i in firsts:
            if i + 1 >= len(close) or close[i] <= 0:
                continue
            if close_pos[i] < CLOSE_POS_MIN:
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
            recs.append({'D': idx[i], 'chg': chg[i], 'close_pos': close_pos[i],
                         'ret': ret, 'hold': hold})
        out[t] = recs
    return out


def build(thresholds: List[float], limit: Optional[int] = None) -> Dict[float, pd.DataFrame]:
    files = [f for f in os.listdir(PKL_DIR) if f.endswith('.pkl')]
    if limit:
        files = files[:limit]
    acc = {t: [] for t in thresholds}
    for n, fname in enumerate(files, 1):
        if n % 500 == 0:
            print(f'  ... {n}/{len(files)} 종목 스캔', flush=True)
        res = scan_one(os.path.join(PKL_DIR, fname), thresholds)
        for t, recs in res.items():
            if recs:
                code = fname[:-4]
                for r in recs:
                    r['code'] = code
                acc[t].extend(recs)
    return {t: pd.DataFrame(v) for t, v in acc.items()}


def net(ret: pd.Series) -> float:
    """왕복비용 차감 후 평균 %."""
    return float(ret.mean()) - COST * 100


def summarize(X: pd.DataFrame, label: str, years: List[int]):
    n = len(X)
    print(f'{label:<14}{n:>9,}{net(X["ret"]):>11.3f}{X["ret"].median():>10.3f}'
          f'{(X["ret"] > 0).mean() * 100:>8.1f}%{X["hold"].mean():>9.2f}', end='')
    for y in years:
        sub = X[X['D'].dt.year == y]
        print(f'{net(sub["ret"]) if len(sub) > 100 else float("nan"):>10.3f}', end='')
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--years', type=str, default='2024,2025,2026')
    ap.add_argument('--limit', type=int, default=None, help='pkl 개수 제한(빠른 확인용)')
    args = ap.parse_args()
    years = [int(y) for y in args.years.split(',')]

    print('pkl 스캔 중 (2,858종목, 수 분 소요)...', flush=True)
    data = build([2.0, 3.0], limit=args.limit)
    T2, T3 = data[2.0], data[3.0]

    hdr = (f'{"구분":<14}{"건수":>9}{"비용후%":>11}{"중앙%":>10}{"승률":>9}{"보유일":>9}'
           + ''.join(f'{y:>10}' for y in years))

    print('\n' + '=' * len(hdr))
    print('A. 문턱 전체 비교 — 같은 파이프라인(첫신호일 + 종가위치>=0.6 + 손절-6%/5일)')
    print('=' * len(hdr))
    print(hdr)
    print('-' * len(hdr))
    summarize(T3, '문턱 3% (기존)', years)
    summarize(T2, '문턱 2% (변경)', years)
    print()

    print('=' * len(hdr))
    print('B. 등락률 구간별 성과 (문턱 2% 파이프라인 안에서)')
    print('=' * len(hdr))
    print(hdr)
    print('-' * len(hdr))
    buckets = [('2~3% (신규)', 2, 3), ('3~5%', 3, 5), ('5~8%', 5, 8),
               ('8~12%', 8, 12), ('12~20%', 12, 20), ('20%+', 20, 1e9)]
    for lab, lo, hi in buckets:
        sub = T2[(T2['chg'] >= lo) & (T2['chg'] < hi)]
        if len(sub) < 100:
            print(f'{lab:<14}{len(sub):>9,}   (표본부족)')
            continue
        summarize(sub, lab, years)
    print()

    # 문턱을 내리면 '2~3% 신규 편입'뿐 아니라 기존 종목의 진입일도 앞당겨진다.
    # 그 두 효과를 분리해서 보여준다.
    new_band = T2[(T2['chg'] >= 2) & (T2['chg'] < 3)]
    rest2 = T2[T2['chg'] >= 3]
    print('=' * len(hdr))
    print('C. 효과 분해 — 신규 편입분 vs 기존 구간(진입일이 앞당겨진 영향 포함)')
    print('=' * len(hdr))
    print(hdr)
    print('-' * len(hdr))
    summarize(T3, '문턱3의 3%+', years)
    summarize(rest2, '문턱2의 3%+', years)
    summarize(new_band, '문턱2의 2~3%', years)
    print()
    print(f'신호 수 변화: {len(T3):,} → {len(T2):,}건 ({len(T2) / max(1, len(T3)) - 1:+.1%})')
    print(f'  이 중 2~3% 신규 편입 {len(new_band):,}건, '
          f'3%+ 구간도 {len(T3):,} → {len(rest2):,}건으로 변함(클러스터 시작일 이동)')


if __name__ == '__main__':
    main()
