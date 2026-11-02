import requests
import json
import time
import threading
import uuid
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import Dict, List
from flask import current_app, jsonify

from utils.toss_openapi import get_trading_amounts as get_amounts

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
    # 2026-10-23: c-chart 계열이 _browserId 쿠키가 없으면 400 invalid-request를 돌려준다(실측:
    # 값은 아무 UUID나 되고 로그인 쿠키·app-version·browser-tab-id는 불필요, 쿠키 이름만 필수).
    "Cookie": "_browserId=" + uuid.uuid4().hex,
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
#
# 2026-10-30: 비공식 c-chart가 막혀 공식 Open API로 교체(utils/toss_openapi.py). 거래대금 상위 100위는
# 랭킹의 실제 값, 그 밖은 일봉 거래량 x 대표가격 근사. 10초 캐시는 그쪽에서 처리한다.
def get_trading_amounts(stk_cds: List[str]) -> Dict[str, float]:
    """종목코드 리스트 -> {종목코드: 오늘 거래대금(원)}. 조회 실패한 종목은 결과에서 빠진다
    (표시용 부가 정보라 실패해도 화면이 죽으면 안 됨)."""
    return get_amounts(stk_cds)


# ── 종목 뉴스 (2026-09-08, 관심종목 추천 리포트용) ───────────────────────────
# request_stock_info_with_toss_api()는 Flask 요청 컨텍스트(current_app.logger)에 의존해서
# 스케줄러 잡(요청 컨텍스트 밖)에서 그대로 못 쓴다 — get_trading_amounts()와 같은 이유로
# Flask에 의존하지 않는 별도 함수로 둔다.
def get_stock_news(stock_name: str, limit: int = 3) -> List[Dict]:
    """종목명으로 최근 뉴스 최대 limit건을 [{id, title, source, created_at, url}, ...]로 반환.
    실패하면 빈 리스트(표시용 부가 데이터라 화면/리포트가 죽으면 안 됨).

    2026-10-30: 토스 NEWS(비공식 검색 API)가 400으로 막혔고 공식 Open API엔 뉴스가 없다.
    Google News RSS(공개 피드)로 교체했다 — 최근 7일 기사만, 제목은 'OO - 매체' 꼴이라 매체명을
    떼어 source로 분리한다. url은 news.google.com 리다이렉트 링크(클릭하면 원문 매체로 이동)라
    프런트가 검색 링크 대신 이걸 쓸 수 있다. created_at은 ISO 8601(UTC). 같은 종목을 한 리포트에서
    여러 번 부르지 않지만, 피드 부담을 줄이려 1시간 캐시한다."""
    key = (stock_name, limit)
    now = time.time()
    with _NEWS_CACHE_LOCK:
        cached = _NEWS_CACHE.get(key)
        if cached and now - cached[0] < _NEWS_CACHE_TTL:
            return cached[1]
    try:
        res = requests.get(
            _NEWS_RSS_URL,
            params={"q": f"{stock_name} 주식 when:7d", "hl": "ko", "gl": "KR", "ceid": "KR:ko"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        res.raise_for_status()
        out = []
        for it in ET.fromstring(res.content).findall("./channel/item")[:limit]:
            title = it.findtext("title") or ""
            src_el = it.find("source")
            source = src_el.text if src_el is not None else None
            if source and title.endswith(" - " + source):
                title = title[:-len(" - " + source)]
            try:
                created_at = parsedate_to_datetime(it.findtext("pubDate")).isoformat()
            except Exception:
                created_at = None
            link = it.findtext("link")
            out.append({"id": link, "title": title, "source": source, "created_at": created_at, "url": link})
        with _NEWS_CACHE_LOCK:
            _NEWS_CACHE[key] = (now, out)
        return out
    except Exception as e:
        print(f"[WARN] get_stock_news 실패: {stock_name} {e}")
        return []


_NEWS_RSS_URL = "https://news.google.com/rss/search"
_NEWS_CACHE_LOCK = threading.Lock()
_NEWS_CACHE: Dict[tuple, tuple] = {}
_NEWS_CACHE_TTL = 3600.0


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
