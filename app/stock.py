from datetime import datetime

from flask import Blueprint, render_template, jsonify, request, send_file, send_from_directory, session, url_for, redirect, Response, stream_with_context
from flask_login import login_required, current_user
from app.repository.stocks.StockDTO import StockDTO
from app.repository.stocks.stocks import merge_daily_interest_stocks, get_interest_stocks, get_interest_stocks_info, \
    update_stock_list, get_stock_list, delete_delisted_stock, update_interest_stock_graph, \
    update_interest_stock_list_close, upsert_favorite_stocks, get_favorite_stocks, get_favorite_stocks_info_api, \
    update_low_stock_graph, update_interest_stock_close_correctly_list, find_stocks_by_name_prefix
from app.repository.users.users import find_user_by_username
import time
from utils.request_toss_api import request_stock_overview_with_toss_api, request_stock_info_with_toss_api, \
    request_stock_volume_and_amount, request_stock_category
from job.batch_runner import predict_stock_graph
from config.config import settings
from job.kiwoom_api import get_holdings_and_summary, get_account_credentials, get_current_price_and_name
from job.kiwoom_trailing_stop import get_trade_history, get_pnl_summary, get_asset_based_pnl, manual_buy, manual_sell

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

@stock.route("/interest/data/today", methods=["POST"])
def get_interesting_stocks():
    data = request.json
    date = data.get("date")
    target = data.get("target") or 'interest'
    stocks = get_interest_stocks(date, date,"normal")
    return stocks

@stock.route("/interest/data/fire", methods=["POST"])
def get_interesting_stocks_info():
    data = request.json
    date = data.get("date")
    endDate = data.get("endDate", datetime.today())
    stocks = get_interest_stocks_info(date, endDate)
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
    result = upsert_favorite_stocks(s)
    return {"status": "success", "result": result}, 200


@stock.route("/favorite", methods=["GET"])
@login_required
def fetch_favorite_stocks():
    fetch_user = find_user_by_username(session["_user_id"])
    stocks = get_favorite_stocks(fetch_user.id)
    return jsonify(stocks)

@stock.route("/interest/data/favorite", methods=["POST"])
@login_required
def get_favorite_stocks_data():
    data = request.json
    date = data.get("date")
    endDate = data.get("endDate")

    # print("_user_id =", session.get("_user_id"))
    # print("current_user.id =", getattr(current_user, "id", None))

    fetch_user = find_user_by_username(session["_user_id"])
    if fetch_user is not None:
        user_id = fetch_user.id
    else:
        user_id = None

    stocks = get_interest_stocks_info(date, endDate, user_id)
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

@stock.route("/interest/data/favorite/schedule", methods=["POST"])
def get_favorite_stocks_data_schedule():
    data = request.json
    # date = data.get("date")

    stocks = get_favorite_stocks_info_api(None)
    return stocks


# ── 키움 모의투자 대시보드 (내 종목 탭) ──────────────────────────────────────

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
        price, stk_nm = get_current_price_and_name(stk_cd)
    except Exception as e:
        print(e)
        return {"status": "error", "message": str(e)}, 500
    return jsonify({"stk_cd": stk_cd, "stk_nm": stk_nm, "price": price})


@stock.route("/kiwoom/holdings", methods=["GET"])
@login_required
def get_kiwoom_holdings():
    acnt_no, acnt_pwd = get_account_credentials()
    if not (acnt_no and acnt_pwd):
        return {"status": "error", "message": "계좌 정보가 설정되지 않음"}, 500
    try:
        holdings, summary = get_holdings_and_summary(acnt_no, acnt_pwd)
        asset_pnl = get_asset_based_pnl(summary['total_asset'])
    except Exception as e:
        print(e)
        return {"status": "error", "message": str(e)}, 500
    return jsonify({"holdings": holdings, "summary": summary, "asset_pnl": asset_pnl})


@stock.route("/kiwoom/history", methods=["GET"])
@login_required
def get_kiwoom_history():
    limit = request.args.get("limit", 200, type=int)
    try:
        history = get_trade_history(limit)
        pnl_summary = get_pnl_summary()
    except Exception as e:
        print(e)
        return {"status": "error", "message": str(e)}, 500
    return jsonify({"history": history, "pnl_summary": pnl_summary})


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
        result = manual_buy(stk_cd, int(qty) if qty else None)
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
        result = manual_sell(stk_cd, int(qty))
    except Exception as e:
        print(e)
        return {"status": "error", "message": str(e)}, 500
    return jsonify({"status": "success", "result": result})



