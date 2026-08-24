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
    mark_stock_viewed, get_viewed_stocks
from app.repository.users.users import find_user_by_username
import time
from utils.request_toss_api import request_stock_overview_with_toss_api, request_stock_info_with_toss_api, \
    request_stock_volume_and_amount, request_stock_category
from job.batch_runner import predict_stock_graph
from config.config import settings
from auto_trading.kiwoom_api import get_holdings_and_summary, get_account_credentials, \
    get_current_price_and_name, get_deposit, get_unfilled_orders, KIWOOM_ENV, VALID_ENVS
from auto_trading.kiwoom_trailing_stop import get_trade_history, get_pnl_summary, get_asset_based_pnl, manual_buy, manual_sell, manual_cancel_order
from auto_trading import kiwoom_v8_strategy as v8_strategy

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
        asset_pnl = get_asset_based_pnl(summary['total_asset'], env)
        # 예수금은 kt00018 에 없어서 별도 조회(kt00001). 없으면 화면이 죽지 않게 None 으로 넘긴다.
        try:
            summary['deposit'] = get_deposit(acnt_no, acnt_pwd, env)
        except Exception as de:
            print(f'예수금 조회 실패: {de}')
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
    out = [{
        'rank': i + 1,
        'stk_cd': c.get('code'),
        'stk_nm': c.get('name'),
        'ord_px': c.get('ord_px'),
        'cur_px': c.get('cur_px'),
        'gap': c.get('gap'),
        'live_gap': c.get('live_gap'),
        'score': c.get('score'),
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


