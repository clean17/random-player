import os
import json
from datetime import datetime

from flask import Blueprint, render_template, jsonify, request, send_file, send_from_directory, session, url_for, redirect, Response, stream_with_context
from flask_login import login_required, current_user
from app.repository.stocks.StockDTO import StockDTO
from app.repository.stocks.stocks import merge_daily_interest_stocks, get_interest_stocks, get_interest_stocks_info, \
    update_stock_list, get_stock_list, delete_delisted_stock, update_interest_stock_graph, \
    update_interest_stock_list_close, upsert_favorite_stocks, get_favorite_stocks, get_favorite_stocks_info_api, \
    get_favorite_stocks_latest, \
    update_low_stock_graph, update_interest_stock_close_correctly_list, find_stocks_by_name_prefix, \
    upsert_reserved_stocks, get_reserved_stocks, clear_reserved_stocks, \
    mark_stock_viewed, get_viewed_stocks, get_logo_urls_by_codes
from app.repository.users.users import find_user_by_username
import time
from utils.request_toss_api import request_stock_overview_with_toss_api, request_stock_info_with_toss_api, \
    request_stock_volume_and_amount, request_stock_category
from job.batch_runner import predict_stock_graph
from config.config import settings
from auto_trading.kiwoom_api import get_holdings_and_summary, get_holdings, get_account_credentials, \
    get_current_price_and_name, get_deposit, get_unfilled_orders, env_path, KIWOOM_ENV, VALID_ENVS
from auto_trading.kiwoom_trailing_stop import get_trade_history, get_pnl_summary, get_asset_based_pnl, manual_buy, manual_sell, manual_cancel_order, \
    _held_business_days as _legacy_business_days
from auto_trading import kiwoom_trailing_stop as legacy_exit
from auto_trading import kiwoom_v8_strategy as v8_strategy
from auto_trading import kiwoom_v8_exit
from auto_trading.kiwoom_v8_exit import _business_days as _v8_business_days

stock = Blueprint('stocks', __name__)


def _is_guest():
    return hasattr(current_user, 'username') and current_user.username == settings['GUEST_USERNAME']




@stock.route("/predict-stocks/<stock>", methods=['POST'], endpoint='predict-kospi')
@login_required
def predict_stocks(stock):
    predict_stock_graph(stock)
    if stock == 'kospi':
        stock_name = '코스피'
    if stock == 'nasdaq':
        stock_name = '나스닥'
    return {"status": "success", "message": stock_name+" 예측 시작!!"}

kospi_progress = {
    "percent": 0.0,
    "count": 0,
    "total_count": 0,
    "ticker": "",
    "stock_name": "",
    "done": False
}
nasdaq_progress = {
    "percent": 0.0,
    "count": 0,
    "total_count": 0,
    "ticker": "",
    "stock_name": "",
    "done": False
}

@stock.route("/progress/<stock>")
@login_required
def get_progress(stock):
    if stock == 'kospi':
        return jsonify(kospi_progress)
    if stock == 'nasdaq':
        return jsonify(nasdaq_progress)


@stock.route("/progress-update/<stock>", methods=["POST"])
def update_progress(stock):
    data = request.json
    if stock == 'kospi':
        kospi_progress["percent"] = data.get("percent", 0)
        kospi_progress["count"] = data.get("count", 0)
        kospi_progress["total_count"] = data.get("total_count", 0)
        kospi_progress["ticker"] = data.get("ticker", "")
        kospi_progress["stock_name"] = data.get("stock_name", "")
        kospi_progress["done"] = data.get("done", False)
        return jsonify(kospi_progress)
    if stock == 'nasdaq':
        nasdaq_progress["percent"] = data["percent"]
        nasdaq_progress["done"] = data.get("done", False)
        nasdaq_progress["count"] = data.get("count", 0)
        nasdaq_progress["total_count"] = data.get("total_count", 0)
        nasdaq_progress["ticker"] = data.get("ticker", "")
        nasdaq_progress["stock_name"] = data.get("stock_name", "")
        return jsonify(nasdaq_progress)

@stock.route("/interest/insert", methods=["POST"])
def upsert_interesting_stocks():
    s = StockDTO.from_json(request.json)
    if not s.target:
        s.target = 'interest'

    update_interest_stock_list_close([(s.current_price, None, s.logo_image_url, s.stock_code)])
    result = merge_daily_interest_stocks(s)
    return {"status": "success", "result": result}, 200


@stock.route("/interest/correct/list", methods=["POST"])
def update_interest_stock_close_correct_list():
    data = request.json or {}
    items = data.get("items") or []

    if not isinstance(items, list):
        return {"status": "fail", "message": "items must be list"}, 400

    stocks = [
        StockDTO.from_json(item)
        for item in items
        if item.get("stock_code") and item.get("last_close") and item.get("created_at")
    ]

    result = update_interest_stock_close_correctly_list(stocks)
    return {
        "status": "success",
        "request_count": len(items),
        "update_target_count": len(stocks),
        "result": result
    }, 200


@stock.route("/interest/graph", methods=["POST"])
def update_interesting_stocks_graph():
    result = update_interest_stock_graph(StockDTO.from_json(request.json))
    return {"status": "success", "result": result}, 200

@stock.route("/low/graph", methods=["POST"])
def update_low_stocks_graph():
    result = update_low_stock_graph(StockDTO.from_json(request.json))
    return {"status": "success", "result": result}, 200

# 1_periodically_update_today_interest_stocks.py 에서 호출하여 가격을 주기적으로 갱신하기 위함
@stock.route("/interest/data/today", methods=["POST"])
def get_interesting_stocks():
    data = request.json
    date = data.get("date")
    target = data.get("target") or 'interest'
    stocks = get_interest_stocks(date, date, "normal", target_value=target)
    return stocks

@stock.route("/interest/data/fire", methods=["POST"])
def get_interesting_stocks_info():
    data = request.json
    date = data.get("date")
    endDate = data.get("endDate", datetime.today())
    target_value = data.get("target") or 'interest'
    stocks = get_interest_stocks_info(date, endDate, target_value=target_value)
    return stocks

@stock.route("/interest/data/low", methods=["POST"])
def get_low_stocks():
    data = request.json
    date = data.get("date")
    endDate = data.get("endDate") or date
    rule = data.get("rule") or None
    stocks = get_interest_stocks(date, endDate, "low", rule=rule)
    return stocks

@stock.route("/interest/view", methods=["GET"])
@login_required
def get_view_of_interesting_stocks():
    return render_template("interesting_stocks.html", version=int(time.time()))


@stock.route("/update", methods=["POST"])
def update_stocks():
    stocks = [StockDTO.from_json(d) for d in request.json]
    try:
        update_stock_list(stocks)
    except Exception as e:
        print(e)
        return {"status": "error", "message": str(e)}, 500
    return {"status": "success", "result": "200"}, 200

# 주식 종목 리스트 갱신 후 상장폐지된 종목 flag 수정
@stock.route("/delisted-stock", methods=["POST"])
def delete_delisted_stock_stocks():
    try:
        delete_delisted_stock()
    except Exception as e:
        # 오류 발생시 JSON 반환
        return {
            "status": "error",
            "message": str(e)
        }, 500

    return {"status": "success", "result": "200"}, 200


@stock.route("/<nation>", methods=["GET"])
def get_stocks(nation):
    return get_stock_list(nation)

# 종목명 검색 > productCode
@stock.route("/info", methods=["POST"])
def get_realtime_price():
    data = request.json
    stock_name = data.get('stock_name') or ""

    result = request_stock_info_with_toss_api(stock_name)

    # 에러 형식이면 status code 같이 내려주기
    if isinstance(result, dict) and not result.get("success", True):
        return jsonify(result), 502  # Bad Gateway or 503 등

    return jsonify(result)

# 요약 정보
@stock.route("/overview", methods=["POST"])
def get_stock_overview():
    data = request.json
    product_code = data.get('product_code') or ""
    result = request_stock_overview_with_toss_api(product_code)

    if not result.get("success", False):
        return jsonify(result), 502

    return jsonify(result["data"])

# 시총 가져오기
@stock.route("/amount", methods=["POST"])
def get_stock_amount():
    data = request.json
    product_code = data.get('product_code') or ""
    return request_stock_volume_and_amount(product_code)

# 회사 정보 가져오기
@stock.route("/company", methods=["POST"])
def get_stock_company_info():
    data = request.json
    company_code = data.get('company_code') or ""
    return request_stock_category(company_code)


@stock.route("/favorite", methods=["POST"])
@login_required
def upsert_favorite_stock():
    s = StockDTO.from_json(request.json)
    s.user_id = find_user_by_username(session["_user_id"]).id
    row_id, flag = upsert_favorite_stocks(s)
    # flag는 토글이 반영된 뒤의 서버 실제 값 — 클라이언트는 자기가 추측한 상태 대신 이 값으로 그린다.
    return {"status": "success", "result": row_id, "flag": bool(flag)}, 200


@stock.route("/favorite", methods=["GET"])
@login_required
def fetch_favorite_stocks():
    fetch_user = find_user_by_username(session["_user_id"])
    stocks = get_favorite_stocks(fetch_user.id)
    return jsonify(stocks)

@stock.route("/interest/data/favorite", methods=["POST"])
@login_required
def get_favorite_stocks_data():
    # 즐겨찾기는 기간 집계가 아니라 종목별 최신 스냅샷 1건만 보여준다 (실시간 탭과 동일한 형태).
    fetch_user = find_user_by_username(session["_user_id"])
    user_id = fetch_user.id if fetch_user is not None else None

    stocks = get_favorite_stocks_latest(user_id)
    return stocks

@stock.route("/interest/data/favorite/heart", methods=["POST"])
@login_required
def get_favorite_heart_stocks_data():
    data = request.json
    date = data.get("date")
    endDate = data.get("endDate")

    fetch_user = find_user_by_username(session["_user_id"])
    if fetch_user is not None:
        user_id = fetch_user.id
    else:
        user_id = None

    stocks = get_interest_stocks_info(date, endDate, user_id)
    return stocks

@stock.route("/reserved", methods=["POST"])
@login_required
def upsert_reserved_stock():
    """자동매수 대상 토글 (favorite와 동일하게 flag를 뒤집는 upsert)."""
    s = StockDTO.from_json(request.json)
    s.user_id = find_user_by_username(session["_user_id"]).id
    row_id, flag = upsert_reserved_stocks(s)
    return {"status": "success", "result": row_id, "flag": bool(flag)}, 200


@stock.route("/reserved", methods=["GET"])
@login_required
def fetch_reserved_stocks():
    fetch_user = find_user_by_username(session["_user_id"])
    stocks = get_reserved_stocks(fetch_user.id)
    return jsonify(stocks)


@stock.route("/reserved/clear-all", methods=["POST"])
@login_required
def clear_all_reserved_stocks():
    """자동매수 대상 전체를 flag=false로 일괄 해제."""
    fetch_user = find_user_by_username(session["_user_id"])
    count = clear_reserved_stocks(fetch_user.id)
    return {"status": "success", "cleared": count}, 200


@stock.route("/viewed", methods=["POST"])
@login_required
def upsert_viewed_stock():
    """카드를 한 번이라도 확인(클릭)했음을 기록. 토글이 아니라 항상 True로 upsert."""
    s = StockDTO.from_json(request.json)
    s.user_id = find_user_by_username(session["_user_id"]).id
    row_id = mark_stock_viewed(s)
    return {"status": "success", "result": row_id}, 200


@stock.route("/viewed", methods=["GET"])
@login_required
def fetch_viewed_stocks():
    fetch_user = find_user_by_username(session["_user_id"])
    stocks = get_viewed_stocks(fetch_user.id)
    return jsonify(stocks)


@stock.route("/interest/data/reserved", methods=["POST"])
@login_required
def get_reserved_stocks_data():
    data = request.json
    date = data.get("date")
    endDate = data.get("endDate")

    fetch_user = find_user_by_username(session["_user_id"])
    user_id = fetch_user.id if fetch_user is not None else None

    stocks = get_interest_stocks_info(date, endDate, user_id, source='reserved')
    return stocks


@stock.route("/interest/data/favorite/schedule", methods=["POST"])
def get_favorite_stocks_data_schedule():
    data = request.json
    # date = data.get("date")

    stocks = get_favorite_stocks_info_api(None)
    return stocks


# ── 키움 대시보드 (내 계좌 탭) ────────────────────────────────────────────────
# 2026-08-20: 모의/실전을 화면에서 골라 볼 수 있게 env 파라미터를 받는다.
# 스케줄러(자동매매)는 여전히 .env의 KIWOOM_ENV 하나만 쓴다 — 여기서 바꾸는 건 조회/수동주문 대상뿐이다.


def _req_env(from_json: bool = False):
    """요청에서 kiwoom 환경을 읽어 검증. 값이 없으면 None(=프로세스 기본값)을 반환한다.

    ⚠️ 매수/매도에도 이 값이 쓰인다. 화면에 모의 계좌를 띄운 채 실전으로 주문이 나가면 안 되므로
       프런트는 조회와 주문에 **같은 env**를 보내야 한다.
    """
    raw = ((request.get_json(silent=True) or {}).get("env") if from_json
           else request.args.get("env"))
    raw = (raw or "").strip().lower()
    if not raw:
        return None
    if raw not in VALID_ENVS:
        raise ValueError(f"env는 {'/'.join(VALID_ENVS)} 중 하나여야 합니다: {raw!r}")
    return raw


@stock.route("/kiwoom/envs", methods=["GET"])
@login_required
def get_kiwoom_envs():
    """선택 가능한 계좌 환경과, 스케줄러가 실제로 돌고 있는 기본 환경."""
    return jsonify({
        "envs": list(VALID_ENVS),
        "default": KIWOOM_ENV,          # .env의 KIWOOM_ENV — 자동매매가 붙어 있는 계좌
        "labels": {"real": "실전", "mock": "모의"},
    })


@stock.route("/kiwoom/lookup-code", methods=["GET"])
@login_required
def get_kiwoom_lookup_code():
    name = (request.args.get("name") or "").strip()
    if not name:
        return jsonify({"matches": []})
    try:
        matches = find_stocks_by_name_prefix(name)
    except Exception as e:
        print(e)
        return {"status": "error", "message": str(e)}, 500
    return jsonify({"matches": matches})


@stock.route("/kiwoom/price", methods=["GET"])
@login_required
def get_kiwoom_price():
    stk_cd = (request.args.get("stk_cd") or "").strip()
    if not stk_cd:
        return {"status": "error", "message": "stk_cd is required"}, 400
    try:
        env = _req_env()
        price, stk_nm = get_current_price_and_name(stk_cd, env=env)
    except Exception as e:
        print(e)
        return {"status": "error", "message": str(e)}, 500
    return jsonify({"stk_cd": stk_cd, "stk_nm": stk_nm, "price": price})


def _load_v8_positions(env):
    """kiwoom_v8_exit.py 의 포지션 상태(entry/atr/peak/trail_armed/tp_done)를 읽는다.

    kiwoom_v8_exit.STATE_PATH 는 그 모듈이 import될 때의 프로세스 KIWOOM_ENV로 고정돼 있어
    (v8_strategy._load_state_for_env() 와 같은 이유, kiwoom_v8_strategy.py:736-742 주석 참고)
    대시보드(Flask)에서 env 파라미터로 실전/모의를 오갈 때 그대로 쓰면 계좌가 섞인다.
    경로를 env_path()로 매번 다시 계산해서 우회한다. 조회 전용 — 실매매 로직은 안 건드림.
    """
    path = env_path(os.path.join(os.path.dirname(kiwoom_v8_exit.__file__),
                                  'kiwoom_v8_positions.json'), env)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f'v8 포지션 상태 로드 실패: {e}')
        return {}


def _v8_holding_state(pos, cur_price):
    """보유종목 카드에 붙일 v8 청산상태 요약. pos 는 kiwoom_v8_positions.json 의 종목별 값.

    2026-08-28: 손절/익절까지 남은 폭은 뺐다 — ATR 손절은 이 종목군(급등 후 진입) 특성상
    3×ATR이 고점에서 30%+ 떨어진 곳에 걸려 실측상 한 번도 발동한 적이 없고(로그 0건 확인),
    익절까지는 대부분 음수로만 나와 오히려 헷갈렸다. 지금 실제로 값이 바뀌는 트레일링
    무장상태와 익절 '완료' 여부만 남긴다.
    """
    entry = float(pos.get('entry') or 0)
    peak = float(pos.get('peak') or 0)
    cur = float(cur_price or 0)
    if entry <= 0 or peak <= 0 or cur <= 0:
        return None
    return {
        'type': 'v8',
        'hold_days': _v8_business_days(pos.get('entry_date', '')),
        'max_hold_days': kiwoom_v8_exit.MAX_HOLD_DAYS,
        'pullback_from_peak': cur / peak - 1.0,           # 현재가가 고점 대비 몇 % 아래인지(음수)
        'trail_pct': kiwoom_v8_exit.TRAIL_PCT,             # 트레일링 트리거 폭(예: 0.05 = -5%)
        'trail_armed': bool(pos.get('trail_armed', True)),
        'tp_done': bool(pos.get('tp_done', False)),
    }


def _load_legacy_positions(env):
    """kiwoom_trailing_stop.py 의 레거시 청산 상태(kiwoom_trailing_state.json) — 모의(fire)
    전량, 실전은 v8이 안 산 잔존 종목만 여기 해당한다. v8과 같은 이유로 env별 경로 재계산."""
    path = env_path(os.path.join(os.path.dirname(legacy_exit.__file__),
                                  'kiwoom_trailing_state.json'), env)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f'레거시 청산 상태 로드 실패: {e}')
        return {}


def _legacy_holding_state(pos, avg_price, cur_price):
    """보유종목 카드에 붙일 레거시(fire/구 트레일링) 청산상태 요약. 2026-08-28 추가 —
    모의투자는 v8이 아니라 이 엔진을 쓰므로 v8 배지가 못 뜨던 걸 보완한다.
    TRAILING_ENABLED=False라 트레일링/목표가는 표시할 게 없다(둘 다 비활성) — 실제로
    동작 중인 손절(-6%, 60/90초 재확인)과 보유상한만 보여준다."""
    avg = float(avg_price or 0)
    cur = float(cur_price or 0)
    if avg <= 0 or cur <= 0 or pos.get('exited'):
        return None
    rate = cur / avg - 1.0
    peak_rate = pos.get('peak_rate')
    was_armed = peak_rate is not None and peak_rate >= legacy_exit.TRAIL_ACTIVATE_RATE
    stop_level = legacy_exit.ARMED_GIVEBACK_STOP if was_armed else legacy_exit.STOP_LOSS_RATE
    stop_px = avg * (1.0 + stop_level)
    return {
        'type': 'legacy',
        'hold_days': _legacy_business_days(pos.get('entry_date')),
        'max_hold_days': legacy_exit.MAX_HOLD_DAYS,
        'stop_margin': (cur / stop_px - 1.0) if stop_px > 0 else None,  # 0 이하면 손절권
        'stop_level': stop_level,
        'watching': pos.get('stop_watch_since') is not None,  # 손절선 재확인 대기 중
    }


def _day_change_rate_from_pkl(stk_cd):
    """당일 등락률 = pkl 마지막 두 종가의 비율 - 1. kt00018의 pred_close_pric은 실측상
    cur_prc와 항상 같은 값이 와서(키움 쪽 결함으로 보임, 2026-08-28 확인) 못 쓴다.

    "오늘 날짜" 기준으로 전일종가를 찾는 대신(prev_close_of), pkl의 **마지막 두 행을
    그대로** 쓴다 — 이러면 장중엔 자동으로 '오늘(진행중) vs 어제'가 되고, 장마감 후부터
    다음 거래일 pkl이 갱신되기 전까지는 자동으로 '방금 마감된 세션 vs 그 전날'이 유지된다
    (다른 증권사 앱들이 마감 후에도 그날 등락률을 계속 보여주는 것과 같은 동작 — 시간으로
    구분선을 긋지 않고 '데이터가 실제로 갱신됐는가'로 자연히 구분된다)."""
    try:
        if not stk_cd:
            return None
        d = v8_strategy._load_daily(stk_cd)
        if d is None or len(d) < 2:
            return None
        close = d['close']
        prev_close = float(close.iloc[-2])
        return float(close.iloc[-1]) / prev_close - 1.0 if prev_close > 0 else None
    except Exception:
        return None


@stock.route("/kiwoom/holdings", methods=["GET"])
@login_required
def get_kiwoom_holdings():
    try:
        env = _req_env()
    except ValueError as e:
        return {"status": "error", "message": str(e)}, 400
    acnt_no, acnt_pwd = get_account_credentials(env)
    if not (acnt_no and acnt_pwd):
        return {"status": "error",
                "message": f"계좌 정보가 설정되지 않음 (env={env or KIWOOM_ENV})"}, 500
    try:
        holdings, summary = get_holdings_and_summary(acnt_no, acnt_pwd, env)
        # 청산상태(보유일/트리거까지 남은 정도) — v8이 산 종목은 v8 규칙, 그 외(모의 fire 전량 +
        # 실전에서 v8이 안 산 잔존 종목)는 레거시 트레일링 엔진 규칙을 쓴다(2026-08-28, 모의투자엔
        # 이게 전부라 이걸 안 붙이면 청산상태 칸이 항상 비어 있었다). 둘 다 상태 파일에 없으면 None.
        v8pos = _load_v8_positions(env)
        legacy_pos = _load_legacy_positions(env)
        # 종목 아이콘용 로고 — stocks 테이블에 있으면 그걸 쓰고, 없으면 프론트에서
        # 토스 증권 아이콘(https://static.toss.im/png-icons/securities/icn-sec-fill-{code}.png)으로
        # 폴백한다(2026-08-28). DB 조회 1건으로 일괄 처리.
        logo_urls = get_logo_urls_by_codes([h.get('stk_cd') for h in holdings if h.get('stk_cd')])
        for h in holdings:
            code = h.get('stk_cd')
            v8p = v8pos.get(code)
            exit_state = _v8_holding_state(v8p, h.get('cur_price')) if v8p else None
            if exit_state is None:
                lp = legacy_pos.get(code)
                if lp:
                    exit_state = _legacy_holding_state(lp, h.get('avg_price'), h.get('cur_price'))
            h['v8'] = exit_state
            h['logo_url'] = logo_urls.get(code)
            # 2026-08-28: kt00018의 pred_close_pric(전일종가)이 cur_prc와 항상 똑같이 와서
            # (실측 확인 — 키움 API 쪽 결함으로 보임) day_change_rate가 매번 0%로 나왔다.
            # pkl 일봉의 실제 전일 종가로 다시 계산해서 덮어쓴다.
            h['day_change_rate'] = _day_change_rate_from_pkl(h.get('stk_cd'))
        asset_pnl = get_asset_based_pnl(summary['total_asset'], env)
        # 2026-08-28: 원래 "1회 투입금(ALLOC=8%) 참고값"으로 넣었었는데, 사용자가 원한 건
        # 그게 아니라 "지금 실제 미체결 매수 주문에 얼마가 걸려있는지"였다 — 그 돈은 평가금(체결
        # 전이라 안 잡힘)에도 보유현금(ord_alow_amt는 이미 이만큼 빼고 남은 값)에도 안 보여서
        # 따로 보여줘야 한다. 매수 주문만 카운트(매도 미체결은 종목을 묶지 현금을 안 묶는다).
        try:
            unfilled = get_unfilled_orders(acnt_no, acnt_pwd, env=env)
            summary['pending_order_amount'] = sum(
                float(o.get('ord_pric_num') or 0) * int(o.get('oso_qty_num') or 0)
                for o in unfilled if '매수' in str(o.get('io_tp_nm') or '')
            )
        except Exception as e:
            print(f'미체결 매수주문 금액 계산 실패: {e}')
            summary['pending_order_amount'] = None
        # 예수금은 kt00018 에 없어서 별도 조회(kt00001). 없으면 화면이 죽지 않게 None 으로 넘긴다.
        # 2026-08-27: 실패 시 1회 재시도 — 순간적인 레이트리밋/타임아웃이면 이걸로 대부분
        # 넘어간다. 재시도까지 실패하면 프론트가 '총자산-평가금액' 근사식으로 대체 표시하던
        # 시절이 있었는데, 그 근사식은 계좌가 거의 풀 투자 상태일 때 부호가 뒤집혀 없던
        # 미수금처럼(오늘 모의계좌 -50만원 오표시) 보이는 게 이미 확인된 결함이라 지금은
        # 프론트에서 그 폴백을 쓰지 않는다(interesting_stocks.html renderMyStocksSummary 참고).
        try:
            summary['deposit'] = get_deposit(acnt_no, acnt_pwd, env)
        except Exception as de:
            print(f'예수금 조회 실패, 재시도: {de}')
            try:
                summary['deposit'] = get_deposit(acnt_no, acnt_pwd, env)
            except Exception as de2:
                print(f'예수금 조회 재시도도 실패: {de2}')
                summary['deposit'] = None
    except Exception as e:
        print(e)
        return {"status": "error", "message": str(e)}, 500
    return jsonify({"holdings": holdings, "summary": summary, "asset_pnl": asset_pnl,
                    "env": env or KIWOOM_ENV})


@stock.route("/kiwoom/history", methods=["GET"])
@login_required
def get_kiwoom_history():
    limit = request.args.get("limit", 200, type=int)
    try:
        env = _req_env()
        history = get_trade_history(limit, env)
        pnl_summary = get_pnl_summary(env)
    except ValueError as e:
        return {"status": "error", "message": str(e)}, 400
    except Exception as e:
        print(e)
        return {"status": "error", "message": str(e)}, 500
    return jsonify({"history": history, "pnl_summary": pnl_summary,
                    "env": env or KIWOOM_ENV})


@stock.route("/kiwoom/orders", methods=["GET"])
@login_required
def get_kiwoom_orders():
    try:
        env = _req_env()
    except ValueError as e:
        return {"status": "error", "message": str(e)}, 400
    acnt_no, acnt_pwd = get_account_credentials(env)
    if not (acnt_no and acnt_pwd):
        return {"status": "error",
                "message": f"계좌 정보가 설정되지 않음 (env={env or KIWOOM_ENV})"}, 500
    try:
        raw = get_unfilled_orders(acnt_no, acnt_pwd, env=env)
    except Exception as e:
        print(e)
        return {"status": "error", "message": str(e)}, 500

    # gap/score는 v8 후보 캐시(당일자)에만 있다. v8이 아닌 주문(레거시 fire/manual)은 None.
    cands = v8_strategy.get_today_candidates_by_code(env)
    owned = v8_strategy.get_owned_codes_for_env(env)

    orders = []
    for r in raw:
        code = str(r.get('stk_cd') or '')
        io = str(r.get('io_tp_nm') or '')
        side = 'buy' if '매수' in io else ('sell' if '매도' in io else io)
        tm = str(r.get('tm') or '')
        ord_tm = f'{tm[0:2]}:{tm[2:4]}:{tm[4:6]}' if len(tm) == 6 else tm
        cand = cands.get(code)
        orders.append({
            'ord_no': r.get('ord_no'),
            'stk_cd': code,
            'stk_nm': r.get('stk_nm'),
            'side': side,
            'ord_qty': r.get('ord_qty_num'),
            'ord_pric': r.get('ord_pric_num'),
            'oso_qty': r.get('oso_qty_num'),
            'cur_prc': r.get('cur_prc_num'),
            'ord_tm': ord_tm,
            'gap': cand.get('gap') if cand else None,
            'score': cand.get('score') if cand else None,
            'v8_owned': code in owned,
        })
    orders.sort(key=lambda o: o.get('ord_tm') or '', reverse=True)
    return jsonify({"orders": orders, "env": env or KIWOOM_ENV})


@stock.route("/kiwoom/live_gap_ranking", methods=["GET"])
@login_required
def get_kiwoom_live_gap_ranking():
    """v8 후보 상위 N개의 실시간(현재가 기준) gap 순위. 종목당 현재가 조회 1회씩 필요해
    N=60이면 ~8~9초 걸린다 — 프론트에서 수동 새로고침으로만 호출해야 한다(자동 폴링 금지)."""
    try:
        env = _req_env()
    except ValueError as e:
        return {"status": "error", "message": str(e)}, 400
    top_n = request.args.get("top", 60, type=int)
    try:
        ranking = v8_strategy.get_live_gap_ranking(env, top_n)
    except Exception as e:
        print(e)
        return {"status": "error", "message": str(e)}, 500

    # 지금 실제로 보유 중인 종목인지 + 보유금액(평가금액) — 후보 목록만 봐도 바로 알 수 있게
    # (2026-08-28). evltv_prft가 아니라 cur_price*qty로 계산 — 이 화면 목적상 kt00018의
    # 원단위 반올림 오차는 무시할 만하고, 보유종목 탭과 같은 계산식을 쓰는 게 더 중요하다.
    held_value = {}
    try:
        acnt_no, acnt_pwd = get_account_credentials(env)
        if acnt_no and acnt_pwd:
            held_value = {h.get('stk_cd'): float(h.get('cur_price') or 0) * float(h.get('qty') or 0)
                          for h in get_holdings(acnt_no, acnt_pwd, env)}
    except Exception as e:
        print(f'live_gap_ranking 보유종목 조회 실패: {e}')

    out = [{
        'rank': i + 1,
        'stk_cd': c.get('code'),
        'stk_nm': c.get('name'),
        'ord_px': c.get('ord_px'),
        'cur_px': c.get('cur_px'),
        'gap': c.get('gap'),
        'live_gap': c.get('live_gap'),
        'score': c.get('score'),
        'owned': c.get('code') in held_value,
        'holding_value': held_value.get(c.get('code')),
    } for i, c in enumerate(ranking)]
    return jsonify({"ranking": out, "env": env or KIWOOM_ENV})


@stock.route("/kiwoom/buy", methods=["POST"])
@login_required
def post_kiwoom_buy():
    if _is_guest():
        return {"status": "error", "message": "게스트는 매수할 수 없습니다"}, 403

    data = request.get_json() or {}
    stk_cd = data.get("stk_cd")
    qty = data.get("qty")
    if not stk_cd:
        return {"status": "error", "message": "stk_cd is required"}, 400

    try:
        env = _req_env(from_json=True)
        result = manual_buy(stk_cd, int(qty) if qty else None, env=env)
    except ValueError as e:
        return {"status": "error", "message": str(e)}, 400
    except Exception as e:
        print(e)
        return {"status": "error", "message": str(e)}, 500
    return jsonify({"status": "success", "result": result})


@stock.route("/kiwoom/sell", methods=["POST"])
@login_required
def post_kiwoom_sell():
    if _is_guest():
        return {"status": "error", "message": "게스트는 매도할 수 없습니다"}, 403

    data = request.get_json() or {}
    stk_cd = data.get("stk_cd")
    qty = data.get("qty")
    if not stk_cd or not qty:
        return {"status": "error", "message": "stk_cd, qty is required"}, 400

    try:
        env = _req_env(from_json=True)
        result = manual_sell(stk_cd, int(qty), env=env)
    except ValueError as e:
        return {"status": "error", "message": str(e)}, 400
    except Exception as e:
        print(e)
        return {"status": "error", "message": str(e)}, 500
    return jsonify({"status": "success", "result": result})


@stock.route("/kiwoom/cancel_order", methods=["POST"])
@login_required
def post_kiwoom_cancel_order():
    if _is_guest():
        return {"status": "error", "message": "게스트는 주문을 취소할 수 없습니다"}, 403

    data = request.get_json() or {}
    stk_cd = data.get("stk_cd")
    ord_no = data.get("ord_no")
    side = data.get("side")
    qty = data.get("qty") or 0
    if not stk_cd or not ord_no or side not in ("buy", "sell"):
        return {"status": "error", "message": "stk_cd, ord_no, side(buy/sell)는 필수입니다"}, 400

    try:
        env = _req_env(from_json=True)
        result = manual_cancel_order(stk_cd, ord_no, side, int(qty), env=env)
    except ValueError as e:
        return {"status": "error", "message": str(e)}, 400
    except Exception as e:
        print(e)
        return {"status": "error", "message": str(e)}, 500
    return jsonify({"status": "success", "result": result})


