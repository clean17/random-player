# -*- coding: utf-8 -*-
"""interest_stocks 1년 이력으로 '언제 사야 기대수익이 가장 높은가' 분석 (2026-08-14 작성).

지금 fire 전략은 get_interest_stocks_info()에서 signal_days BETWEEN 2 AND 3 인 종목을
총상승률 낮은순으로 산다. 그 선택이 최선인지, 다른 진입 시점이 나은지 데이터로 확인한다.

검증하는 '시점' 축
  1. 신호 차수      : 같은 종목의 신호 묶음(cluster) 안에서 몇 번째 신호일에 사는가
  2. 누적 신호일수  : 그 시점까지 신호가 며칠 쌓였는가 (현재 조건 = 2~3일)
  3. 최초 신호 후 경과일
  4. 요일 / 신호 발생 시각
  5. 신호 당시 총상승률(첫 신호가 대비 상승폭)

수익률은 pkl 종가 기준 N거래일 보유. 위험(MDD·하방)도 같이 낸다 — 평균만 보면 오판한다.
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

from auto_trading.backtest.fire_backtest_regen import load_ohlc  # noqa: E402

CLUSTER_GAP = 6      # 이 영업일 이상 신호가 끊기면 다른 묶음으로 본다 (FIRE_WINDOW_DAYS와 동일)
FWD_LIST = [1, 3, 5]


def load_signals():
    from config.db_connect import db_pool
    with db_pool.connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT stock_code, stock_name, created_at, target,
                   today_price_change_pct, current_trading_value, avg5d_trading_value,
                   market_value
              FROM interest_stocks
             ORDER BY stock_code, created_at
        """)
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=['code', 'name', 'created_at', 'target',
                                     'chg', 'tv', 'avg5tv', 'mv'])
    df['D'] = pd.to_datetime(df['created_at']).dt.normalize()
    df['hour'] = pd.to_datetime(df['created_at']).dt.hour
    for c in ('chg', 'tv', 'avg5tv', 'mv'):
        df[c] = pd.to_numeric(df[c], errors='coerce')
    # 같은 종목·같은 날 중복(여러 target)은 하나로
    df = df.sort_values(['code', 'created_at']).drop_duplicates(['code', 'D'], keep='first')
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fwd', type=int, default=3)
    args = ap.parse_args()

    sig = load_signals()
    print(f'신호 {len(sig):,}건 / {sig["code"].nunique():,}종목 / '
          f'{sig["D"].min().date()} ~ {sig["D"].max().date()}\n')

    # ── 신호 묶음(cluster)과 차수 계산 ──────────────────────────────────────
    recs = []
    for code, g in sig.groupby('code'):
        ohlc = load_ohlc(code)
        if ohlc is None:
            continue
        g = g.sort_values('D')
        gap = g['D'].diff().dt.days
        cluster = (gap.isna() | (gap > CLUSTER_GAP)).cumsum()
        g = g.assign(cluster=cluster)
        for cid, cg in g.groupby('cluster'):
            first_d = cg['D'].iloc[0]
            for n, (_, r) in enumerate(cg.iterrows(), start=1):
                i = ohlc.index.searchsorted(r['D'])
                if i >= len(ohlc) or ohlc.index[i] != r['D']:
                    continue
                entry = float(ohlc['종가'].iloc[i])
                if entry <= 0:
                    continue
                rec = {'code': code, 'D': r['D'], 'nth': n,
                       'days_since_first': int((r['D'] - first_d).days),
                       'cluster_size': len(cg), 'chg': r['chg'], 'hour': r['hour'],
                       'dow': r['D'].dayofweek, 'target': r['target'],
                       'tv_ratio': (r['tv'] / r['avg5tv'] * 100) if r['avg5tv'] else np.nan,
                       'mv': r['mv'],
                       # 묶음 첫 신호일 종가 대비 현재 상승폭 = 프론트의 '총상승률'에 대응
                       'total_rate': None}
                fi = ohlc.index.searchsorted(first_d)
                if fi < len(ohlc) and ohlc.index[fi] == first_d:
                    fp = float(ohlc['종가'].iloc[fi])
                    if fp > 0:
                        rec['total_rate'] = (entry / fp - 1) * 100
                for f in FWD_LIST:
                    j = i + f
                    rec[f'fwd{f}'] = (float(ohlc['종가'].iloc[j]) / entry - 1) * 100 if j < len(ohlc) else np.nan
                lows = ohlc['저가'].iloc[i + 1:i + 1 + args.fwd]
                rec['mdd'] = (float(lows.min()) / entry - 1) * 100 if len(lows) else np.nan
                recs.append(rec)

    X = pd.DataFrame(recs).dropna(subset=[f'fwd{args.fwd}'])
    print(f'수익률 매칭 {len(X):,}건 (보유 {args.fwd}거래일 기준)\n')

    F = f'fwd{args.fwd}'
    hdr = (f'{"구분":<22}{"건수":>8}{"평균%":>9}{"중앙%":>9}{"승률":>8}'
           f'{"MDD%":>8}{"1일%":>8}{"5일%":>8}')

    def show(title, groups):
        print('=' * 88)
        print(title)
        print('=' * 88)
        print(hdr)
        print('-' * 88)
        for label, sub in groups:
            if len(sub) < 100:
                print(f'{label:<22}{len(sub):>8,}   (표본부족)')
                continue
            print(f'{label:<22}{len(sub):>8,}{sub[F].mean():>9.3f}{sub[F].median():>9.3f}'
                  f'{(sub[F] > 0).mean() * 100:>7.1f}%{sub["mdd"].mean():>8.2f}'
                  f'{sub["fwd1"].mean():>8.3f}{sub["fwd5"].mean():>8.3f}')
        print()

    show('전체 기준선', [('전체', X)])

    show('1. 신호 차수 (묶음 내 몇 번째 신호일에 매수)',
         [(f'{n}번째 신호일', X[X['nth'] == n]) for n in range(1, 7)])

    show('2. 누적 신호일수 = 묶음 크기 (현재 조건: 2~3)',
         [(f'묶음 {n}일짜리', X[X['cluster_size'] == n]) for n in range(1, 7)] +
         [('묶음 7일 이상', X[X['cluster_size'] >= 7])])

    show('3. 최초 신호 후 경과일',
         [('당일(0일)', X[X['days_since_first'] == 0]),
          ('1~2일', X[(X['days_since_first'] >= 1) & (X['days_since_first'] <= 2)]),
          ('3~5일', X[(X['days_since_first'] >= 3) & (X['days_since_first'] <= 5)]),
          ('6일 이상', X[X['days_since_first'] >= 6])])

    show('4. 신호 당시 총상승률 (첫 신호가 대비)',
         [('0% 이하', X[X['total_rate'] <= 0]),
          ('0~5%', X[(X['total_rate'] > 0) & (X['total_rate'] <= 5)]),
          ('5~10%', X[(X['total_rate'] > 5) & (X['total_rate'] <= 10)]),
          ('10~20%', X[(X['total_rate'] > 10) & (X['total_rate'] <= 20)]),
          ('20% 초과', X[X['total_rate'] > 20])])

    show('5. 요일', [(d, X[X['dow'] == i]) for i, d in enumerate(['월', '화', '수', '목', '금'])])

    show('6. 당일 등락률',
         [('3% 미만', X[X['chg'] < 3]), ('3~5%', X[(X['chg'] >= 3) & (X['chg'] < 5)]),
          ('5~8%', X[(X['chg'] >= 5) & (X['chg'] < 8)]),
          ('8~12%', X[(X['chg'] >= 8) & (X['chg'] < 12)]),
          ('12% 이상', X[X['chg'] >= 12])])

    show('7. 거래대금비 (당일/5일평균 %)',
         [('100% 미만', X[X['tv_ratio'] < 100]),
          ('100~150%', X[(X['tv_ratio'] >= 100) & (X['tv_ratio'] < 150)]),
          ('150~300%', X[(X['tv_ratio'] >= 150) & (X['tv_ratio'] < 300)]),
          ('300% 이상', X[X['tv_ratio'] >= 300])])

    # 최적 조합 탐색 — 상위 조건을 겹쳐본다
    print('=' * 88)
    print('8. 조합 — 위에서 좋았던 조건을 겹쳤을 때')
    print('=' * 88)
    print(hdr)
    print('-' * 88)
    best = X[(X['nth'] == 1) & (X['tv_ratio'] < 150)]
    print(f'{"1번째신호 & 거래대금비<150":<22}{len(best):>8,}{best[F].mean():>9.3f}'
          f'{best[F].median():>9.3f}{(best[F] > 0).mean() * 100:>7.1f}%'
          f'{best["mdd"].mean():>8.2f}{best["fwd1"].mean():>8.3f}{best["fwd5"].mean():>8.3f}')
    b2 = X[(X['nth'] == 1) & (X['total_rate'] <= 5) & (X['tv_ratio'] < 150)]
    print(f'{"+ 총상승률<=5%":<22}{len(b2):>8,}{b2[F].mean():>9.3f}'
          f'{b2[F].median():>9.3f}{(b2[F] > 0).mean() * 100:>7.1f}%'
          f'{b2["mdd"].mean():>8.2f}{b2["fwd1"].mean():>8.3f}{b2["fwd5"].mean():>8.3f}')


if __name__ == '__main__':
    main()
