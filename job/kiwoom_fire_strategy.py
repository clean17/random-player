# -*- coding: utf-8 -*-
"""
fire(급상승 관심종목) 자동 매수 전략.

매수 조건 (2026-08-05 기준):
  1. 시장폭 레짐 ON      : 전 종목 중 종가>MA20 비율 >= 40% (BREADTH_MIN). 미만이면 그날 진입 전면 차단
  2. fire 쿼리 통과      : get_interest_stocks_info(오늘-6일 ~ 오늘)를 총상승률 내림차순으로 받음.
                           쿼리 자체 조건(총상승률 8~12%, 당일 3~12%, 고점 대비 -3% 이내,
                           시총 700억↑, 거래대금 40억↑ 등)은 SQL에 있음
  3. reserved 교집합     : 위를 통과한 종목 중, 관심종목 화면에서 '자동매수 대상'으로 체크한
                           종목(reserved_stocks, flag=true)만 남긴다. 체크한 게 없으면 그날 매수 없음.
                           체크했어도 fire 조건을 못 넘기면 사지 않는다(교집합).
                           스케줄러엔 로그인 세션이 없어 user 구분 없이 flag=true 전체를 본다.
  4. 보유/쿨다운 제외    : 이미 보유 중이거나 COOLDOWN_DAYS(7일) 내 재매수면 skip
  5. 사이징             : 기준은 총자산이 아니라 '가용 현금'(총자산 - 보유종목 평가금액).
                           가용현금 × CASH_DEPLOY_RATIO(70%)까지만 쓰고 나머지 30%는 버퍼로 남긴다.
                           그 금액을 BUY_SLOTS(7)등분 → 1픽당 가용현금의 10%, 하루 최대 7종목.
                           교집합이 7종목보다 많으면 총상승률 높은 순으로 7개까지만.
                           1픽 예산보다 주가가 비싸면(1주도 못 삼) 그 종목은 skip하고 다음 후보로.

백테스트 근거 (fire_backtest_result.csv, 2025-09 ~ 2026-07, 2,658건):
  - fire 픽 전체 매수: 평균 +0.39%/건 (수수료 빼면 본전 이하)
  - H2 필터(20일 신고가 -1.6% 이내 + 당일 등락률 +12% 이상): 평균 +2.75%, 승률 48.6%
  - H2 + 시장폭 레짐: 평균 +3.50%, 승률 53%, 9개월 전부 플러스

  ⚠️ 2026-08-05 요청으로 H2 필터를 제거함. 위 백테스트 기준으로는 H2 없는 'fire 픽 전체 매수'가
     평균 +0.39%/건(수수료 차감 시 본전 이하) 구간에 해당한다. 다만 그 수치는 fire 픽 전체를 대상으로
     한 것이고 지금은 총상승률 상위 10개로 한정 + 레짐 필터가 남아 있어 완전히 같은 조건은 아니다.
     성과는 재검증이 필요하며, 되돌리려면 get_fire_candidates()에 _daily_metrics() 조건을 다시 걸면 된다.

진입 시점 (중요):
  백테스트의 매수가는 신호일 '종가'다(fire_backtest_result.csv의 buy 컬럼 = 해당일 종가로 확인됨).
  H2 필터도 20일 신고가 대비/당일 등락률이라 완성된 일봉을 전제한 지표다. 따라서 이 전략은
  장 마감 직전 1회만 평가/매수한다 (batch_runner의 kiwoom_fire_buy 잡, 평일 15:18).
  예전처럼 장중 :15/:35/:55로 21번 돌리면 아직 절반만 만들어진 일봉으로 판단하게 되고,
  급등 중인 장중 고점을 추격해 하루 매수 한도(BUY_SLOTS)를 아침에 소진한다. 실제로 2026-07-24
  HD현대에너지솔루션은 10:35에 196,600원에 샀는데 그날 종가가 164,000원(-16.6%),
  SK오션플랜트는 10:55에 20,450원에 샀는데 종가 18,350원(-10.3%)이었다.

매수 후 청산은 kiwoom_trailing_stop.py의 30초 잡이 자동으로 담당한다
(손절 -6.5% / 되돌림손절 -3% / 목표 10·15·20% 1/3씩 / 트레일링).

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
CHECK_DISPLAY_LIMIT = 20   # --check로 후보를 출력할 때만 쓰는 표시 개수 제한 (매수 로직과 무관)
BREADTH_MIN = 0.40         # 시장폭 레짐: 전 종목 중 종가>MA20 비율 40% 이상일 때만 진입
FIRE_WINDOW_DAYS = 6       # fire 집계 기간 (오늘-6일 ~ 오늘, 프론트 '관심' 탭과 동일)
CASH_DEPLOY_RATIO = 0.70   # 가용 현금 중 자동매수에 쓸 최대 비율 (나머지 30%는 현금 버퍼로 남김)
BUY_SLOTS = 7              # 위 금액을 7등분 → 1픽당 '가용현금 × 70% ÷ 7' = 가용현금의 10%.
                           # 하루 최대 신규 매수 종목 수이기도 함
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

def _daily_metrics(stk_cd: str) -> Optional[Tuple[float, float]]:
    """(dist_20d_high %, ret_1d %) 반환 — 로그/사후분석용 참고 지표. 매수 필터로는 쓰지 않는다.
    pkl 데이터가 오늘자가 아니면 None (장중 20분 주기 갱신 전제)."""
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


def get_fire_candidates(limit: Optional[int] = None) -> List[Dict]:
    """fire 쿼리(SQL 조건 통과) 결과를 총상승률 내림차순으로 반환.
    SQL이 ORDER BY total_rate_of_increase DESC로 내려주므로 순서를 그대로 쓴다.
    limit은 출력용 제한일 뿐, 매수 경로에서는 자르지 않는다 — 자르면 내가 체크한(reserved) 종목이
    순위가 낮다는 이유로 조용히 제외돼 '체크했는데 왜 안 사지?'가 되기 때문.
    (예전엔 여기서 H2 필터로 한 번 더 걸렀으나 2026-08-05 요청으로 제거 — 상단 docstring 참고)"""
    from app.repository.stocks.stocks import get_interest_stocks_info
    today = datetime.date.today()
    start = (today - datetime.timedelta(days=FIRE_WINDOW_DAYS)).isoformat()
    rows = get_interest_stocks_info(start, today.isoformat())
    if limit is not None:
        rows = rows[:limit]

    candidates = []
    for row in rows:
        stk_cd = str(row.get('stock_code') or '').zfill(6)
        if not stk_cd or stk_cd == '000000':
            continue
        metrics = _daily_metrics(stk_cd)  # 참고 지표(로그용) — 없어도 매수는 진행
        candidates.append({
            'stk_cd': stk_cd,
            'stk_nm': row.get('stock_name'),
            'total_rate': row.get('total_rate_of_increase'),
            'dist_20d_high': round(metrics[0], 2) if metrics else None,
            'ret_1d': round(metrics[1], 2) if metrics else None,
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

    # 자동매수 대상(reserved) 교집합 — 화면(관심종목 뷰)에서 체크한 종목만 실제로 매수한다.
    # fire SQL 조건을 통과한 것 중에서 고르는 방식이라, 체크했더라도 그날 조건을 못 넘기면 안 산다.
    from app.repository.stocks.stocks import get_reserved_stock_codes
    try:
        reserved = get_reserved_stock_codes()
    except Exception as e:
        # 조회 실패 시 '전 종목 매수'로 흘러가면 안 되므로 보수적으로 중단
        _log.error(f'[fire] reserved 목록 조회 실패 — 매수 보류: {e}')
        return

    if not reserved:
        _log.info('[fire] 자동매수 대상(reserved)으로 체크된 종목이 없어 매수하지 않음')
        return

    passed = len(candidates)
    candidates = [c for c in candidates if c['stk_cd'] in reserved]
    _log.info(f'[fire] fire 조건 통과 {passed}종목 / reserved {len(reserved)}종목 '
              f'→ 교집합 {len(candidates)}종목')
    if not candidates:
        return

    state = _load_fire_state()
    today = datetime.date.today()
    daily = state.get('_daily', {})
    buys_today = daily.get('count', 0) if daily.get('date') == today.isoformat() else 0
    if buys_today >= BUY_SLOTS:
        return

    holdings, summary = get_holdings_and_summary(ACNT_NO, ACNT_PWD)
    held = {h['stk_cd'] for h in holdings}

    # 사이징 기준은 총자산이 아니라 '가용 현금'. 그중 CASH_DEPLOY_RATIO(70%)까지만 쓰고
    # 나머지 30%는 손대지 않는다(버퍼). deploy_limit을 7등분한 금액이 1픽 예산이며,
    # deployed 누적으로 총 사용액이 70%를 넘지 않도록 막는다.
    cash = summary['total_asset'] - summary['tot_evlt_amt']
    deploy_limit = max(0.0, cash) * CASH_DEPLOY_RATIO
    slot_budget = deploy_limit / BUY_SLOTS if BUY_SLOTS > 0 else 0.0
    deployed = 0.0

    if slot_budget <= 0:
        _log.info(f'[fire] 가용 현금 부족 — 현금 {cash:,.0f}원, 매수 예산 {deploy_limit:,.0f}원')
        return

    _log.info(f'[fire] 후보 {len(candidates)}종목 / 가용현금 {cash:,.0f}원 → '
              f'매수한도 {deploy_limit:,.0f}원({CASH_DEPLOY_RATIO:.0%}) '
              f'{BUY_SLOTS}등분 = 1픽당 {slot_budget:,.0f}원')

    for cand in candidates:
        if buys_today >= BUY_SLOTS:
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
        # 1픽 예산과 '한도 잔액' 중 작은 쪽까지만 (마지막 슬롯이 한도를 넘지 않도록)
        spendable = min(slot_budget, deploy_limit - deployed)
        qty = int(spendable // price)
        if qty <= 0:
            _log.info(f'[fire] {cand["stk_nm"]}({stk_cd}) 매수 예산 부족 '
                      f'(1픽 예산 {spendable:,.0f}원 < 현재가 {price:,.0f}원)')
            continue

        trade_value = qty * price
        asset_ratio = (trade_value / summary['total_asset']) if summary['total_asset'] > 0 else 0.0

        ref = ''
        if cand['dist_20d_high'] is not None:
            ref = f'신고가대비 {cand["dist_20d_high"]:+.1f}%, 당일 {cand["ret_1d"]:+.1f}%, '
        result = buy_market(stk_cd, qty)
        deployed += trade_value
        _log.info(f'[fire매수 {buys_today + 1}/{BUY_SLOTS}] {cand["stk_nm"]}({stk_cd}) 현재가={price:,}원 {qty}주 '
                  f'(총상승률 {cand["total_rate"]}, {ref}breadth={breadth:.0%}) '
                  f'거래대금={trade_value:,.0f}원(자산의 {asset_ratio:.1%}) '
                  f'누적 {deployed:,.0f}/{deploy_limit:,.0f}원 → {result}')
        _record_trade(stk_cd, cand['stk_nm'], 'buy', 'fire', qty, price, price, 0.0, asset_ratio=asset_ratio)

        state[stk_cd] = today.isoformat()
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
        cands = get_fire_candidates(limit=CHECK_DISPLAY_LIMIT)
        try:
            from app.repository.stocks.stocks import get_reserved_stock_codes
            reserved = get_reserved_stock_codes()
        except Exception as e:
            reserved = set()
            print(f'  (reserved 목록 조회 실패: {e})')

        hit = [c for c in cands if c['stk_cd'] in reserved]
        print(f'fire 조건 통과 {len(cands)}건(최대 {CHECK_DISPLAY_LIMIT} 표시) / '
              f'reserved {len(reserved)}종목 → 매수 대상 {len(hit)}건 '
              f'(가용현금의 {CASH_DEPLOY_RATIO:.0%}를 {BUY_SLOTS}등분, 최대 {BUY_SLOTS}종목)')
        for i, c in enumerate(cands, 1):
            ref = (f' 신고가대비 {c["dist_20d_high"]:+.1f}% 당일 {c["ret_1d"]:+.1f}%'
                   if c['dist_20d_high'] is not None else ' (pkl 오늘자 없음)')
            mark = '★매수대상' if c['stk_cd'] in reserved else '         '
            print(f'  {i:2d}. {mark} {c["stk_nm"]}({c["stk_cd"]}) 총상승률 {c["total_rate"]}{ref}')
    elif '--run' in sys.argv:
        if is_market_open():
            run_fire_buy_cycle()
        else:
            print('장 시간이 아님')
    else:
        print('사용법: python -m job.kiwoom_fire_strategy --check | --run')
