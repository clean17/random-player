import requests
import json
import time
import threading
from typing import Dict, List
from flask import current_app, jsonify

INFO_URL = "https://wts-info-api.tossinvest.com/api/v3/search-all/wts-auto-complete"
OVERVIEW_URL = "https://wts-info-api.tossinvest.com/api/v2/stock-infos/PRODUCTCODE/overview"
AMOUNT_URL = "https://wts-info-api.tossinvest.com/api/v1/c-chart/kr-s/PRODUCTCODE/day:1"
CATEGORY_URL = "https://wts-info-api.tossinvest.com/api/v2/companies/COMPANYCODE/tics"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://tossinvest.com",
    "Referer": "https://tossinvest.com/",
}

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
    try:
        res = requests.request(
            method,
            url,
            json=json_body,
            headers=DEFAULT_HEADERS,
            timeout=timeout
        )
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


# ── 보유종목 오늘 거래대금 (2026-09-07, 내 계좌 탭 표시용) ──────────────────────
# kt00018(계좌평가잔고내역)엔 거래대금 필드가 없어 종목당 별도 조회가 필요하다.
# 키움 쪽엔 거래대금을 직접 주는 필드가 없어(ka10001엔 거래량만 있음, 거래대금은
# 가격×거래량 근사가 필요) 이미 붙어 있는 토스 캔들 API(amount 필드, 원 단위 그대로 옴)를
# 그대로 쓴다. 종목코드로 productCode를 바로 만들 수 있어(KRX 보통주는 'A'+6자리코드)
# 검색 단계 없이 바로 조회한다.
# 60초 캐시 — 3초 자동새로고침(장중)에 맞춰 매번 부르면 renew_interest_stocks_close에서
# 겪은 것과 같은 Toss 쪽 속도제한(TLS handshake 거부)을 다시 겪는다.
_AMOUNT_CACHE_LOCK = threading.Lock()
_AMOUNT_CACHE: Dict[str, tuple] = {}   # stk_cd -> (timestamp, amount)
_AMOUNT_CACHE_TTL = 60.0


def get_trading_amounts(stk_cds: List[str]) -> Dict[str, float]:
    """종목코드 리스트 -> {종목코드: 오늘 거래대금(원)}. 조회 실패한 종목은 결과에서 빠진다
    (표시용 부가 정보라 실패해도 화면이 죽으면 안 됨)."""
    now = time.time()
    result: Dict[str, float] = {}
    to_fetch = []
    with _AMOUNT_CACHE_LOCK:
        for code in stk_cds:
            cached = _AMOUNT_CACHE.get(code)
            if cached and now - cached[0] < _AMOUNT_CACHE_TTL:
                result[code] = cached[1]
            else:
                to_fetch.append(code)

    for code in to_fetch:
        try:
            url = AMOUNT_URL.replace("PRODUCTCODE", f"A{code}")
            res = requests.get(url, headers=DEFAULT_HEADERS, timeout=5)
            res.raise_for_status()
            amount = res.json()["result"]["candles"][0]["amount"]
            result[code] = amount
            with _AMOUNT_CACHE_LOCK:
                _AMOUNT_CACHE[code] = (now, amount)
        except Exception as e:
            print(f"[WARN] get_trading_amounts 실패: {code} {e}")

    return result


# ── 종목 뉴스 (2026-09-08, 관심종목 추천 리포트용) ───────────────────────────
# request_stock_info_with_toss_api()는 Flask 요청 컨텍스트(current_app.logger)에 의존해서
# 스케줄러 잡(요청 컨텍스트 밖)에서 그대로 못 쓴다 — get_trading_amounts()와 같은 이유로
# Flask에 의존하지 않는 별도 함수로 둔다.
def get_stock_news(stock_name: str, limit: int = 3) -> List[Dict]:
    """종목명으로 최근 뉴스 최대 limit건을 [{title, source, created_at}, ...]로 반환.
    실패하면 빈 리스트(표시용 부가 데이터라 화면/리포트가 죽으면 안 됨)."""
    try:
        res = requests.post(
            INFO_URL,
            json={"query": stock_name, "sections": [{"type": "NEWS"}]},
            headers=DEFAULT_HEADERS,
            timeout=10,
        )
        res.raise_for_status()
        result = res.json().get("result") or []
        items = (result[0].get("data", {}).get("items") or []) if result else []
        return [{
            "title": it.get("title"),
            "source": it.get("source"),
            "created_at": it.get("createdAt"),
        } for it in items[:limit]]
    except Exception as e:
        print(f"[WARN] get_stock_news 실패: {stock_name} {e}")
        return []


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
