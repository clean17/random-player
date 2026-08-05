# -*- coding: utf-8 -*-
"""
fire(급상승 관심종목) 자동 매수 전략.

백테스트 근거 (fire_backtest_result.csv, 2025-09 ~ 2026-07, 2,658건):
  - fire 픽 전체 매수: 평균 +0.39%/건 (수수료 빼면 본전 이하) → 그대로 못 씀
  - H2 필터(20일 신고가 -1.6% 이내 + 당일 등락률 +12% 이상): 평균 +2.75%, 승률 48.6%
  - H2 + 시장폭 레짐(전 종목 중 종가>MA20 비율 >= 40%): 평균 +3.50%, 승률 53%,
    9개월 전부 플러스. 레짐 OFF 구간(2026-07 같은 하락장)은 신규 진입 자체를 차단.

진입 시점 (중요):
  백테스트의 매수가는 신호일 '종가'다(fire_backtest_result.csv의 buy 컬럼 = 해당일 종가로 확인됨).
  H2 필터도 20일 신고가 대비/당일 등락률이라 완성된 일봉을 전제한 지표다. 따라서 이 전략은
  장 마감 직전 1회만 평가/매수한다 (batch_runner의 kiwoom_fire_buy 잡, 평일 15:15).
  예전처럼 장중 :15/:35/:55로 21번 돌리면 아직 절반만 만들어진 일봉으로 판단하게 되고,
  급등 중인 장중 고점을 추격해 MAX_BUYS_PER_DAY를 아침에 소진한다. 실제로 2026-07-24
  HD현대에너지솔루션은 10:35에 196,600원에 샀는데 그날 종가가 164,000원(-16.6%),
  SK오션플랜트는 10:55에 20,450원에 샀는데 종가 18,350원(-10.3%)이었다.

매수 후 청산은 kiwoom_trailing_stop.py의 30초 잡이 자동으로 담당한다
(손절 -6% / 되돌림손절 -3% / 목표 10·15·20% 1/3씩 / 트레일링).

실전 전 반드시 KIWOOM_ENV=mock으로 검증할 것.
"""
import os
import json
import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

from job.kiwoom_api import buy_market, get_holdings_and_summary, get_account_credentials
from job.kiwoom_trailing_stop import _log, _record_trade, is_market_open

# ── 전략 파라미터 ────────────────────────────────────────────────────────────
DIST_20D_HIGH_MIN = -1.6   # 종가가 20일 최고가 대비 -1.6% 이내 (신고가 근접/돌파)
RET_1D_MIN = 12.0          # 당일 등락률 +12% 이상
BREADTH_MIN = 0.40         # 시장폭 레짐: 전 종목 중 종가>MA20 비율 40% 이상일 때만 진입
FIRE_WINDOW_DAYS = 6       # fire 집계 기간 (오늘-6일 ~ 오늘, 프론트 '관심' 탭과 동일)
BUY_PORTION = 0.10         # 1픽당 총자산의 10% 매수
MAX_BUYS_PER_DAY = 3       # 하루 최대 신규 매수 종목 수
COOLDOWN_DAYS = 7          # 같은 종목 재매수 금지 기간

PKL_DIR = r'C:\my-project\AutoSales.py\data\pickle'
_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs', 'kiwoom_trading')
BREADTH_CACHE = os.path.join(_LOG_DIR, 'market_breadth_cache.json')
FIRE_STATE_FILE = os.path.join(os.path.dirname(__file__), 'kiwoom_fire_state.json')

ACNT_NO, ACNT_PWD = get_account_credentials()


# ── 시장폭(breadth) 레짐 ─────────────────────────────────────────────────────

def _compute_breadth() -> Optional[Tuple[str, float]]:
    """전 종목 pkl 스캔: 최신일 기준 (종가 > MA20) 종목 비율. (date_iso, ratio) 반환.
    2,800여 파일을 읽어 2~3분 걸리므로 하루 1회 캐시해서 쓴다."""
    files = [f for f in os.listdir(PKL_DIR) if f.endswith('.pkl')]
    per_date = {}  # date -> [above, total]
    for fname in files:
        try:
            df = pd.read_pickle(os.path.join(PKL_DIR, fname))
            c = df.iloc[:, 3].dropna()  # 종가
            if len(c) < 21:
                continue
            last_date = c.index[-1]
            ma20 = c.tail(20).mean()
            a = per_date.setdefault(last_date, [0, 0])
            a[1] += 1
            if c.iloc[-1] > ma20:
                a[0] += 1
        except Exception:
            continue
    if not per_date:
        return None
    # 파일별 마지막 일자가 다를 수 있으므로(상폐 등) 가장 최신 일자 기준
    latest = max(per_date.keys())
    above, total = per_date[latest]
    if total < 500:
        return None
    return latest.date().isoformat(), above / total


def get_market_breadth(force: bool = False) -> Optional[float]:
    """오늘자 breadth 반환 (일 1회 계산 후 캐시)."""
    today = datetime.date.today().isoformat()
    if not force and os.path.exists(BREADTH_CACHE):
        try:
            with open(BREADTH_CACHE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            if cache.get('date') == today:
                return cache.get('breadth')
        except (json.JSONDecodeError, OSError):
            pass
    result = _compute_breadth()
    if result is None:
        return None
    data_date, breadth = result
    with open(BREADTH_CACHE, 'w', encoding='utf-8') as f:
        json.dump({'date': today, 'data_date': data_date, 'breadth': breadth}, f)
    _log.info(f'[레짐] 시장폭(종가>MA20 비율)={breadth:.1%} (데이터 기준일 {data_date})')
    return breadth


# ── fire 후보 + H2 필터 ─────────────────────────────────────────────────────

def _h2_metrics(stk_cd: str) -> Optional[Tuple[float, float]]:
    """(dist_20d_high %, ret_1d %) 반환. pkl 데이터가 오늘자가 아니면 None (장중 20분 주기 갱신 전제)."""
    path = os.path.join(PKL_DIR, '{}.pkl'.format(stk_cd))
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_pickle(path)
    except Exception:
        return None
    df = df.iloc[:, :4]
    df.columns = ['open', 'high', 'low', 'close']
    df = df.dropna()
    if len(df) < 21:
        return None
    if df.index[-1].date() != datetime.date.today():
        return None  # 오늘 데이터 아직 없음 (fetch_stock_data 갱신 전)
    close = df['close'].iloc[-1]
    prev_close = df['close'].iloc[-2]
    high20 = df['high'].tail(20).max()
    if high20 <= 0 or prev_close <= 0:
        return None
    dist = (close / high20 - 1) * 100
    ret1d = (close / prev_close - 1) * 100
    return dist, ret1d


def get_fire_candidates() -> List[Dict]:
    """fire 쿼리 결과에 H2 필터를 적용한 매수 후보 목록."""
    from app.repository.stocks.stocks import get_interest_stocks_info
    today = datetime.date.today()
    start = (today - datetime.timedelta(days=FIRE_WINDOW_DAYS)).isoformat()
    rows = get_interest_stocks_info(start, today.isoformat())

    candidates = []
    for row in rows:
        stk_cd = str(row.get('stock_code') or '').zfill(6)
        metrics = _h2_metrics(stk_cd)
        if metrics is None:
            continue
        dist, ret1d = metrics
        if dist >= DIST_20D_HIGH_MIN and ret1d >= RET_1D_MIN:
            candidates.append({
                'stk_cd': stk_cd,
                'stk_nm': row.get('stock_name'),
                'dist_20d_high': round(dist, 2),
                'ret_1d': round(ret1d, 2),
            })
    return candidates


# ── 자동 매수 사이클 ─────────────────────────────────────────────────────────

def _load_fire_state() -> Dict:
    if not os.path.exists(FIRE_STATE_FILE):
        return {}
    try:
        with open(FIRE_STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_fire_state(state: Dict):
    with open(FIRE_STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def run_fire_buy_cycle():
    """장중 주기 실행: 레짐 확인 → fire+H2 후보 → 쿨다운/보유중/일일한도 거르고 시장가 매수."""
    if not (ACNT_NO and ACNT_PWD):
        _log.error('[fire] 계좌 정보 미설정')
        return

    breadth = get_market_breadth()
    if breadth is None:
        _log.error('[fire] 시장폭 계산 실패 — 진입 보류')
        return
    if breadth < BREADTH_MIN:
        return  # 레짐 OFF: 조용히 스킵 (레짐 상태는 breadth 계산 시 하루 1회 로그됨)

    candidates = get_fire_candidates()
    if not candidates:
        return

    state = _load_fire_state()
    today = datetime.date.today()
    daily = state.get('_daily', {})
    buys_today = daily.get('count', 0) if daily.get('date') == today.isoformat() else 0
    if buys_today >= MAX_BUYS_PER_DAY:
        return

    holdings, summary = get_holdings_and_summary(ACNT_NO, ACNT_PWD)
    held = {h['stk_cd'] for h in holdings}
    cash = summary['total_asset'] - summary['tot_evlt_amt']
    budget = summary['total_asset'] * BUY_PORTION

    for cand in candidates:
        if buys_today >= MAX_BUYS_PER_DAY:
            break
        stk_cd = cand['stk_cd']
        if stk_cd in held:
            continue
        last_buy = state.get(stk_cd)
        if last_buy:
            try:
                if (today - datetime.date.fromisoformat(last_buy)).days <= COOLDOWN_DAYS:
                    continue
            except ValueError:
                pass

        from job.kiwoom_api import get_current_price
        price = get_current_price(stk_cd)
        if price <= 0:
            continue
        qty = int(min(budget, cash) // price)
        if qty <= 0:
            _log.info(f'[fire] {cand["stk_nm"]}({stk_cd}) 매수 예산 부족 (현금 {cash:,.0f}원)')
            continue

        trade_value = qty * price
        asset_ratio = (trade_value / summary['total_asset']) if summary['total_asset'] > 0 else 0.0

        result = buy_market(stk_cd, qty)
        _log.info(f'[fire매수] {cand["stk_nm"]}({stk_cd}) 현재가={price:,}원 {qty}주 '
                  f'(신고가대비 {cand["dist_20d_high"]:+.1f}%, 당일 {cand["ret_1d"]:+.1f}%, breadth={breadth:.0%}) '
                  f'거래대금={trade_value:,.0f}원(자산의 {asset_ratio:.1%}) → {result}')
        _record_trade(stk_cd, cand['stk_nm'], 'buy', 'fire', qty, price, price, 0.0, asset_ratio=asset_ratio)

        state[stk_cd] = today.isoformat()
        cash -= qty * price
        buys_today += 1
        state['_daily'] = {'date': today.isoformat(), 'count': buys_today}
        _save_fire_state(state)


if __name__ == '__main__':
    import sys
    if '--check' in sys.argv:
        # 매수 없이 현재 레짐/후보만 확인
        b = get_market_breadth(force='--force' in sys.argv)
        print(f'시장폭: {b:.1%}' if b is not None else '시장폭 계산 실패',
              f'(레짐 {"ON" if b is not None and b >= BREADTH_MIN else "OFF"}, 기준 {BREADTH_MIN:.0%})')
        cands = get_fire_candidates()
        print(f'H2 후보 {len(cands)}건:')
        for c in cands:
            print(f'  {c["stk_nm"]}({c["stk_cd"]}) 신고가대비 {c["dist_20d_high"]:+.1f}% 당일 {c["ret_1d"]:+.1f}%')
    elif '--run' in sys.argv:
        if is_market_open():
            run_fire_buy_cycle()
        else:
            print('장 시간이 아님')
    else:
        print('사용법: python -m job.kiwoom_fire_strategy --check | --run')
