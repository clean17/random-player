# -*- coding: utf-8 -*-
"""fire 백테스트 CSV를 '현재 규칙'으로 재생성한다 (2026-08-11 작성).

기존 logs/kiwoom_trading/fire_backtest_result.csv는 2026-07-14 생성본으로,
목표가 +15% / 트레일링 gap 2% / 시간청산 15일이 살아 있던 시절 규칙이다. 현재 코드는
목표가가 없고(TARGET_RATES=[]) 트레일링이 활성 +7% / gap 5% / 보호선 3%로 바뀌었고,
진입 조건도 2026-08-05 H2 필터 제거로 통과 종목이 급증했다(2026-08-11 실측 89종목).
그 불일치를 없애기 위해 신호 재현부터 청산까지 현재 코드 기준으로 다시 만든다.

사용법:
    venv/Scripts/python.exe auto_trading/backtest/fire_backtest_regen.py [옵션]
      --start 2025-09-08   --end 2026-08-10     (기본: interest_stocks 전체 범위, 오늘 제외)
      --target interest | interest_v2           (기본 interest. v2는 2026-08-11 도입돼 데이터 1일뿐)
      --max-hold 60                             (청산 신호가 안 오면 이 거래일 수에서 종가 청산)
      --out logs/kiwoom_trading/fire_backtest_result_current.csv
    ※ psycopg가 필요하므로 venv 파이썬으로 실행해야 한다(WindowsApps 파이썬엔 없음).

━━━ 신호 재현 ━━━
app.repository.stocks.get_interest_stocks_info(D-FIRE_WINDOW_DAYS, D, target_value=...)를
날짜 D마다 호출한다. 즉 SQL 조건(target, 시총 700억↑, signal_days 2~3, 평균/최근 거래대금 40억↑,
last/avg > 0.5)을 코드 중복 없이 그대로 쓴다.
그 뒤 last_date == D 인 행만 남긴다 — 라이브는 endDate=오늘이고 15:18(09시 이후)에 돌아서
SQL의 'b.last_date = %s::date' 조건이 걸리지만, 과거 날짜로 호출하면 그 조건이 빠지기 때문이다.

★ reserved(자동매수 대상) 교집합은 재현하지 않는다 — 과거 체크 이력이 남아 있지 않다.
  따라서 이 CSV는 '내가 전 종목을 reserved로 체크했다면'에 해당하는 상한선이다.
  사이징 검증에서 후보 수를 실제 reserved 규모로 줄여 쓰는 건 auto_trading/backtest/fire_sizing_backtest.py 쪽 일.

━━━ 청산 규칙 (auto_trading/kiwoom_trailing_stop.py에서 값을 직접 import — 상수가 바뀌면 같이 바뀐다) ━━━
  손절        rate <= STOP_LOSS_RATE(-6%) → 잔여 전량. 트레일링 활성 이력이 있으면
              ARMED_GIVEBACK_STOP(-6%) 적용(현재 두 값이 같아 동작 차이 없음).
  트레일링    peak >= TRAIL_ACTIVATE_RATE(+7%)부터 고점 추적.
              트리거선 = max(peak - TRAIL_GAP(5%p), MIN_PROFIT_FLOOR(+3%)).
              트리거선이 보호선(+3%)에 붙어 발동하면 잔여 전량, 아니면 1/3씩(최대 3분할, 3번째는 전량).
              직전 매도 때보다 높은 새 고점을 만들어야 다시 발동.
  정체보호    트레일링이 한 번 나간 뒤 새 고점 없이 (직전 트리거선 - STALL_GAP(6%p))까지 밀리면 잔여 전량.
  목표가      TARGET_RATES=[] → 없음.

━━━ 일봉으로 근사하는 부분 (라이브는 30초 잡이라 완전 재현 불가) ━━━
  1. 하루 처리 순서: 고가로 peak 갱신 → 저가로 트리거 판정(트레일링 먼저, 그 다음 손절).
     실제 일중 경로(고점을 먼저 찍었는지 저점을 먼저 찍었는지)는 일봉으로 알 수 없다.
     이 순서는 '올랐다가 밀린 날'을 라이브와 같게 재현하는 대신, 저점을 먼저 찍고 반등한 날은
     실제보다 불리하게(트리거 발동) 계산한다.
  2. 체결가는 일봉 저가가 아니라 '트리거선 가격'으로 잡는다(기존 CSV와 같은 관례 — 그래서
     기존 CSV의 stop이 정확히 -6.000에 몰려 있었다). 갭하락으로 트리거선을 건너뛴 경우는
     시가로 체결한다.
  3. 신호일 당일은 청산 평가를 하지 않고 D+1부터 본다. 라이브는 15:18 매수 후 NXT 애프터마켓
     (15:30~20:00)에 같은 날 청산이 가능하지만 드물다.
  4. 3분할 매도가 나오면 수량가중 평균 수익률을 ret_pct에 기록한다(포지션 1건 = 1행 유지).
"""
import argparse
import datetime
import os
import sys
from typing import Dict, List, Optional

import pandas as pd

# auto_trading/backtest/ → 저장소 루트까지 세 단계 올라가야 auto_trading 패키지가 import된다
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from auto_trading.kiwoom_fire_strategy_mock import FIRE_WINDOW_DAYS, PKL_DIR, _parse_pct   # noqa: E402
from auto_trading.kiwoom_trailing_stop import (                                   # noqa: E402
    STOP_LOSS_RATE, ARMED_GIVEBACK_STOP, TARGET_RATES,
    TRAIL_ACTIVATE_RATE, TRAIL_GAP, MIN_PROFIT_FLOOR, STALL_GAP,
)

_pkl_cache = {}


def _num(v):
    """psycopg가 내려주는 Decimal/문자열을 float로. 값이 없거나 파싱 불가면 None."""
    if v is None:
        return None
    try:
        return float(str(v).replace(',', '').replace('%', '').strip())
    except ValueError:
        return None


def load_ohlc(code: str) -> Optional[pd.DataFrame]:
    if code in _pkl_cache:
        return _pkl_cache[code]
    path = os.path.join(PKL_DIR, f'{code}.pkl')
    df = None
    if os.path.exists(path):
        try:
            df = pd.read_pickle(path)
            df = df[['시가', '고가', '저가', '종가']].dropna()
            df.index = pd.to_datetime(df.index)
        except Exception:
            df = None
    _pkl_cache[code] = df
    return df


def simulate_exit(ohlc: pd.DataFrame, entry_idx: int, avg_price: float,
                  max_hold: int, same_day_trigger: bool = True) -> Optional[Dict]:
    """현재 청산 규칙을 일봉으로 시뮬레이션. 포지션 전체의 수량가중 수익률을 반환.

    수량은 1.0을 1포지션으로 보고 1/3씩 다룬다(실제 주 수는 사이징이 결정하므로 무관).
    """
    remaining = 1.0
    tranche = 1.0 / 3.0
    thirds_sold = 0
    peak_rate = None
    last_sold_peak = None
    realized = []          # (비중, 수익률)
    exits = []             # 청산 사유 순서

    def rate_at(price):
        return price / avg_price - 1.0

    last_i = min(entry_idx + max_hold, len(ohlc) - 1)
    for i in range(entry_idx + 1, last_i + 1):
        o, h, l = (float(ohlc['시가'].iloc[i]), float(ohlc['고가'].iloc[i]),
                   float(ohlc['저가'].iloc[i]))

        # 1) 고가로 고점(peak) 갱신 — 라이브의 '2) 트레일링 고점 갱신'에 대응
        #    same_day_trigger=False면 이날 갱신된 고점은 '다음 날'부터만 트리거에 쓴다.
        #    일봉으로는 고점을 먼저 찍었는지 저점을 먼저 찍었는지 알 수 없어, 기본값(True)은
        #    같은 날 arm+트리거를 허용해 트레일링을 과대 발동시킨다(홀더에게 불리한 쪽).
        #    False는 그 반대 극단(유리한 쪽)이라, 둘을 같이 돌리면 참값의 범위를 얻는다.
        peak_before_today = peak_rate
        if rate_at(h) >= TRAIL_ACTIVATE_RATE:
            peak_rate = rate_at(h) if peak_rate is None else max(peak_rate, rate_at(h))
        peak_for_trigger = peak_rate if same_day_trigger else peak_before_today

        # 목표가: TARGET_RATES가 비어 있으면 아무 일도 없음. 켜면 고가 기준으로 반영.
        for t in TARGET_RATES:
            if rate_at(h) >= t and thirds_sold < 3:
                thirds_sold += 1
                sell = remaining if thirds_sold >= 3 else min(tranche, remaining)
                realized.append((sell, t))
                remaining -= sell
                exits.append('target')
        if remaining <= 1e-9:
            break

        armed = peak_for_trigger is not None and peak_for_trigger >= TRAIL_ACTIVATE_RATE
        trigger = max(peak_for_trigger - TRAIL_GAP, MIN_PROFIT_FLOOR) if armed else None
        new_peak = armed and (last_sold_peak is None or peak_for_trigger > last_sold_peak)

        # 2) 트레일링 — 저가가 트리거선을 건드렸는지. 갭하락이면 시가로 체결.
        if trigger is not None and new_peak and rate_at(l) <= trigger and thirds_sold < 3:
            fill = trigger if rate_at(o) > trigger else rate_at(o)
            floor_hit = trigger <= MIN_PROFIT_FLOOR + 1e-9
            if floor_hit:
                thirds_sold = 3
                sell = remaining
                exits.append('trailing_floor')
            else:
                thirds_sold += 1
                sell = remaining if thirds_sold >= 3 else min(tranche, remaining)
                exits.append('trailing_gap')
            realized.append((sell, fill))
            remaining -= sell
            last_sold_peak = peak_for_trigger
            if remaining <= 1e-9 or thirds_sold >= 3:
                break

            # 같은 날 이어서 손절선까지 밀렸다면 잔여도 정리 (라이브는 30초 뒤 사이클에서 처리)
            stop_level = ARMED_GIVEBACK_STOP if armed else STOP_LOSS_RATE
            if rate_at(l) <= stop_level:
                fill = stop_level if rate_at(o) > stop_level else rate_at(o)
                realized.append((remaining, fill))
                exits.append('giveback_stop' if armed else 'stop_loss')
                remaining = 0.0
                break
            continue

        # 3) 손절 — 라이브는 손절을 먼저 보지만, 일봉에선 위 트레일링(고점 갱신 후 하락)이
        #    먼저 발동해야 '올랐다가 밀린 날'이 라이브와 같아진다.
        stop_level = ARMED_GIVEBACK_STOP if armed else STOP_LOSS_RATE
        if rate_at(l) <= stop_level:
            fill = stop_level if rate_at(o) > stop_level else rate_at(o)
            realized.append((remaining, fill))
            exits.append('giveback_stop' if armed else 'stop_loss')
            remaining = 0.0
            break

        # 4) 정체 보호 — 트레일링이 나간 뒤 새 고점 없이 추가로 STALL_GAP만큼 더 밀린 경우
        if last_sold_peak is not None and remaining > 1e-9 and thirds_sold < 3:
            gated = peak_for_trigger is None or peak_for_trigger <= last_sold_peak
            if gated:
                trig_used = max(last_sold_peak - TRAIL_GAP, MIN_PROFIT_FLOOR) - STALL_GAP
                if rate_at(l) <= trig_used:
                    fill = trig_used if rate_at(o) > trig_used else rate_at(o)
                    realized.append((remaining, fill))
                    exits.append('stall')
                    remaining = 0.0
                    break

    exit_i = min(i if realized or remaining <= 1e-9 else last_i, last_i)
    if remaining > 1e-9:
        # 청산 신호 없이 끝까지 감 → 마지막 날 종가로 강제 청산.
        # max_hold에 걸린 것과 '일봉 데이터가 거기서 끝난 것'을 구분한다 — 후자는 아직 청산되지
        # 않았을 수도 있는 미완결 포지션이라 최근 구간을 편향시킨다(exit='truncated').
        data_limited = (entry_idx + max_hold) > (len(ohlc) - 1)
        realized.append((remaining, rate_at(float(ohlc['종가'].iloc[last_i]))))
        exits.append('truncated' if data_limited else 'time')
        exit_i = last_i

    if not realized:
        return None
    w = sum(x[0] for x in realized)
    ret = sum(x[0] * x[1] for x in realized) / w if w > 0 else 0.0
    return {
        'ret_pct': ret * 100,
        'exit': exits[0],
        'exit_seq': '|'.join(exits),
        'days': exit_i - entry_idx,
        'tranches': len(realized),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', default=None)
    ap.add_argument('--end', default=None)
    ap.add_argument('--target', default='interest', choices=['interest', 'interest_v2'])
    ap.add_argument('--max-hold', type=int, default=60)
    ap.add_argument('--no-same-day-trigger', action='store_true',
                    help='당일 갱신된 고점을 그날 트리거에 쓰지 않음(낙관 극단). 기본은 허용(비관 극단)')
    ap.add_argument('--out', default='logs/kiwoom_trading/fire_backtest_result_current.csv')
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    from config.db_connect import db_transaction
    from app.repository.stocks.stocks import get_interest_stocks_info

    @db_transaction
    def signal_dates(conn=None):
        with conn.cursor() as cur:
            cur.execute('select distinct created_at::date d from interest_stocks '
                        'where target = %s order by d', (args.target,))
            return [r[0] for r in cur.fetchall()]

    dates = signal_dates()
    today = datetime.date.today()
    # 오늘은 제외 — SQL의 total_rate가 오늘자 신호에 대해 stocks.close(라이브 값)를 쓰므로
    # 과거 재현과 기준이 달라진다. 또 청산 시뮬레이션에 쓸 이후 일봉도 없다.
    dates = [d for d in dates if d < today]
    if args.start:
        dates = [d for d in dates if d >= datetime.date.fromisoformat(args.start)]
    if args.end:
        dates = [d for d in dates if d <= datetime.date.fromisoformat(args.end)]
    print(f'대상 신호일 {len(dates)}일: {dates[0]} ~ {dates[-1]}  (target={args.target})')
    print(f'청산 규칙: 손절 {STOP_LOSS_RATE:.0%} / 되돌림 {ARMED_GIVEBACK_STOP:.0%} / '
          f'목표가 {TARGET_RATES or "없음"} / 트레일링 활성 {TRAIL_ACTIVATE_RATE:.0%} '
          f'gap {TRAIL_GAP:.0%} 보호선 {MIN_PROFIT_FLOOR:.0%} / 정체 {STALL_GAP:.0%} / '
          f'최대보유 {args.max_hold}거래일\n')

    rows = []
    skipped = {'no_pkl': 0, 'no_bar': 0, 'no_future': 0, 'bad_price': 0}
    for n, d in enumerate(dates, 1):
        start = (d - datetime.timedelta(days=FIRE_WINDOW_DAYS)).isoformat()
        cands = get_interest_stocks_info(start, d.isoformat(), target_value=args.target)
        # 라이브(endDate=오늘, 09시 이후)에만 걸리는 'last_date = endDate' 조건을 수동 적용
        cands = [c for c in cands if c.get('last_date') == d]
        for c in cands:
            code = str(c.get('stock_code') or '').zfill(6)
            ohlc = load_ohlc(code)
            if ohlc is None or ohlc.empty:
                skipped['no_pkl'] += 1
                continue
            ts = pd.Timestamp(d)
            if ts not in ohlc.index:
                skipped['no_bar'] += 1
                continue
            i = ohlc.index.get_loc(ts)
            if i >= len(ohlc) - 1:
                skipped['no_future'] += 1
                continue
            buy = float(ohlc['종가'].iloc[i])
            if buy <= 0:
                skipped['bad_price'] += 1
                continue
            r = simulate_exit(ohlc, i, buy, args.max_hold,
                              same_day_trigger=not args.no_same_day_trigger)
            if r is None:
                skipped['no_future'] += 1
                continue
            # SQL/리포지토리는 total_rate_of_increase, increase_per_day를 '12.9%' 같은 문자열로
            # 내려준다(라이브도 _parse_pct로 파싱해서 쓴다). 숫자로 바꿔서 저장해야
            # auto_trading/backtest/fire_sizing_backtest.py의 총상승률 오름차순 정렬이 동작한다.
            # 주의: SQL이 ROUND(...,1)이라 소수 1자리다(구 CSV는 12.94처럼 2자리 — 자체 계산본).
            rows.append({
                'code': code, 'name': c.get('stock_name'), 'D': d.isoformat(), 'buy': buy,
                'count': c.get('count'),
                'avg_chg': _num(c.get('today_price_change_pct')),
                'total_rate': _parse_pct(c.get('total_rate_of_increase')),
                'per_day': _parse_pct(c.get('increase_per_day')),
                'ret_pct': r['ret_pct'], 'exit': r['exit'], 'days': r['days'],
                'exit_seq': r['exit_seq'], 'tranches': r['tranches'],
                'market_value': _num(c.get('market_value')),
                'avg_trading_value': _num(c.get('avg_trading_value')),
            })
        if n % 25 == 0 or n == len(dates):
            print(f'  {n}/{len(dates)}일 처리, 누적 {len(rows)}건')

    df = pd.DataFrame(rows)
    out = args.out
    os.makedirs(os.path.dirname(out), exist_ok=True)
    df.to_csv(out, index=False, encoding='utf-8-sig')
    print(f'\n저장: {out}  ({len(df)}건)')
    print(f'스킵: {skipped}')
    if len(df):
        print(f'\n일별 후보 수: 중위 {df.groupby("D").size().median():.0f} / '
              f'평균 {df.groupby("D").size().mean():.1f} / 최대 {df.groupby("D").size().max()}')
        print(f'건당 수익률: 평균 {df["ret_pct"].mean():+.3f}%  중위 {df["ret_pct"].median():+.3f}%  '
              f'승률 {(df["ret_pct"] > 0).mean():.1%}')
        print(f'평균 보유 {df["days"].mean():.2f}거래일\n')
        print('exit(첫 청산 사유)별:')
        print(df.groupby('exit')['ret_pct'].agg(['count', 'mean', 'median']).round(3).to_string())
        print('\n청산 시퀀스 상위 10:')
        print(df['exit_seq'].value_counts().head(10).to_string())


if __name__ == '__main__':
    main()
