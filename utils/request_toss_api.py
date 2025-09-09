import requests
import json

INFO_URL = "https://wts-info-api.tossinvest.com/api/v3/search-all/wts-auto-complete"
OVERVIEW_URL = "https://wts-info-api.tossinvest.com/api/v2/stock-infos/PRODUCTCODE/overview"
AMOUNT_URL = "https://wts-info-api.tossinvest.com/api/v1/c-chart/kr-s/PRODUCTCODE/day:1"
def request_stock_info_with_toss_api(stock_name):
    payload = {
        "query": stock_name,
        "sections": [
            {"type": "SCREENER"},
            {"type": "PRODUCT", "option": {"addIntegratedSearchResult": "true"}},
            {"type": "TICS"}
        ]
    }
    headers = {"Content-Type": "application/json"}

    res = requests.post(INFO_URL, headers=headers, data=json.dumps(payload))
    return res.json()

def request_stock_overview_with_toss_api(product_code):
    REPLACE_URL = OVERVIEW_URL.replace('PRODUCTCODE', product_code);
    res = requests.get(REPLACE_URL)
    return res.json()

def request_stock_volume_and_amount(product_code):
    REPLACE_URL = AMOUNT_URL.replace('PRODUCTCODE', product_code);
    res = requests.get(REPLACE_URL)
    return res.json()
