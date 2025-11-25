import requests
import json
from flask import current_app, jsonify

INFO_URL = "https://wts-info-api.tossinvest.com/api/v3/search-all/wts-auto-complete"
OVERVIEW_URL = "https://wts-info-api.tossinvest.com/api/v2/stock-infos/PRODUCTCODE/overview"
AMOUNT_URL = "https://wts-info-api.tossinvest.com/api/v1/c-chart/kr-s/PRODUCTCODE/day:1"
CATEGORY_URL = "https://wts-info-api.tossinvest.com/api/v2/companies/COMPANYCODE/tics"
def request_stock_info_with_toss_api(stock_name):
    payload = {
        "query": stock_name,
        "sections": [
            {"type": "SCREENER"},
            # {"type": "NEWS"},
            {"type": "PRODUCT", "option": {"addIntegratedSearchResult": True}},
            {"type": "TICS"}
        ]
    }
    headers = {"Content-Type": "application/json"}

    try:
        res = requests.post(INFO_URL, headers=headers, data=json.dumps(payload), timeout=5)
        res.raise_for_status()  # 4xx/5xx면 예외 발생
        return res.json()
    except requests.exceptions.Timeout as e:
        current_app.logger.error(f"[TOSS INFO] timeout: {e}")
        # 프론트에서 처리하기 싶으면 JSON으로 에러 내려주기
        return {
            "success": False,
            "error": "TOSS_API_TIMEOUT",
            "message": "토스 서버 응답이 지연되고 있습니다.",
        }
    except requests.exceptions.RequestException as e:
        # 모든 requests 관련 에러 (ConnectionError 포함)
        current_app.logger.error(f"[TOSS INFO] request error: {e}")
        return {
            "success": False,
            "error": "TOSS_API_ERROR",
            "message": "토스 서버에 연결할 수 없습니다.",
        }

def request_stock_overview_with_toss_api(product_code):
    REPLACE_URL = OVERVIEW_URL.replace('PRODUCTCODE', product_code);
    try:
        res = requests.get(REPLACE_URL, timeout=5)
        res.raise_for_status()  # 4xx/5xx면 예외 발생
        return res.json()
    except requests.exceptions.Timeout as e:
        current_app.logger.error(f"[TOSS OVERVIEW] timeout: {e}")
        return {
            "success": False,
            "error": "TOSS_TIMEOUT",
            "message": "토스 서버 응답이 지연되고 있습니다.",
        }

    except requests.exceptions.RequestException as e:
        # ConnectionError 포함 모든 requests 에러
        current_app.logger.error(f"[TOSS OVERVIEW] request error: {e}")
        return {
            "success": False,
            "error": "TOSS_REQUEST_ERROR",
            "message": "토스 서버에 연결할 수 없습니다.",
        }

def request_stock_volume_and_amount(product_code):
    REPLACE_URL = AMOUNT_URL.replace('PRODUCTCODE', product_code);
    res = requests.get(REPLACE_URL)
    return res.json()

def request_stock_category(company_code):
    REPLACE_URL = CATEGORY_URL.replace('COMPANYCODE', company_code);
    res = requests.get(REPLACE_URL)
    return res.json()

# print(request_stock_info_with_toss_api('086390'))

def safe_request_json(method, url, **kwargs):
    try:
        res = requests.request(method, url, timeout=5, **kwargs)
        res.raise_for_status()
        return True, res.json()
    except Exception as e:
        current_app.logger.error(f"[HTTP ERROR] {method} {url}: {e}")
        return False, None
'''
ok, data = safe_request_json("GET", REPLACE_URL)
if not ok:
    return {...에러 JSON...}
'''