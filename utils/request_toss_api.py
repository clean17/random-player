import requests
import json
from flask import current_app, jsonify

INFO_URL = "https://wts-info-api.tossinvest.com/api/v3/search-all/wts-auto-complete"
OVERVIEW_URL = "https://wts-info-api.tossinvest.com/api/v2/stock-infos/PRODUCTCODE/overview"
AMOUNT_URL = "https://wts-info-api.tossinvest.com/api/v1/c-chart/kr-s/PRODUCTCODE/day:1"
CATEGORY_URL = "https://wts-info-api.tossinvest.com/api/v2/companies/COMPANYCODE/tics"


def toss_request_json(
        method: str,
        url: str,
        *,
        json_body=None,
        timeout: int = 15,
        log_tag: str = "TOSS",
        timeout_code: str = "TOSS_TIMEOUT",
        error_code: str = "TOSS_REQUEST_ERROR",
        timeout_msg: str = "토스 서버 응답이 지연되고 있습니다.",
        error_msg: str = "토스 서버에 연결할 수 없습니다.",
):
    """
    토스 API 공통 호출 래퍼
    - 성공: res.json() 그대로 리턴
    - 실패: {success: False, error: ..., message: ...} 리턴
    """
    try:
        res = requests.request(method, url, json=json_body, timeout=timeout)
        res.raise_for_status()
        return res.json()
    except requests.exceptions.Timeout as e:
        current_app.logger.error(f"[{log_tag}] timeout: {e}")
        return {
            "success": False,
            "error": timeout_code,
            "message": timeout_msg,
        }
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"[{log_tag}] request error: {e}")
        return {
            "success": False,
            "error": error_code,
            "message": error_msg,
        }


def request_stock_info_with_toss_api(stock_name):
    payload = {
        "query": stock_name,
        "sections": [
            {"type": "SCREENER"},
            # {"type": "NEWS"},
            {"type": "PRODUCT", "option": {"addIntegratedSearchResult": True}},
            {"type": "TICS"},
        ],
    }

    return toss_request_json(
        "POST",
        INFO_URL,
        json_body=payload,
        log_tag="TOSS INFO",
        timeout_code="TOSS_API_TIMEOUT",
        error_code="TOSS_API_ERROR",
    )


def request_stock_overview_with_toss_api(product_code):
    url = OVERVIEW_URL.replace("PRODUCTCODE", product_code)

    return toss_request_json(
        "GET",
        url,
        log_tag="TOSS OVERVIEW",
        timeout_code="TOSS_TIMEOUT",
        error_code="TOSS_REQUEST_ERROR",
    )


def request_stock_volume_and_amount(product_code):
    url = AMOUNT_URL.replace("PRODUCTCODE", product_code)

    return toss_request_json(
        "GET",
        url,
        log_tag="TOSS AMOUNT",
        timeout_code="TOSS_TIMEOUT",
        error_code="TOSS_REQUEST_ERROR",
    )


def request_stock_category(company_code):
    url = CATEGORY_URL.replace("COMPANYCODE", company_code)

    return toss_request_json(
        "GET",
        url,
        log_tag="TOSS CATEGORY",
        timeout_code="TOSS_TIMEOUT",
        error_code="TOSS_REQUEST_ERROR",
    )


# print(request_stock_info_with_toss_api('086390'))
