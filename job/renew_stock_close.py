from typing import Dict, Any
import psycopg
import psycopg_pool
import os
import requests
import time
import uuid
from datetime import datetime, time as dtime

from pathlib import Path
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from utils.wsgi_midleware import logger
from utils.toss_openapi import get_last_prices

sys.path.append(str(Path(__file__).resolve().parents[1]))  # project_root



from datetime import datetime
import pytz
from pykrx import stock


KST = pytz.timezone("Asia/Seoul")


def is_korean_stock_business_day(date=None, verbose=False):
    if date is None:
        date = datetime.now(KST).strftime("%Y%m%d")
    elif isinstance(date, datetime):
        date = date.strftime("%Y%m%d")
    else:
        date = str(date).replace("-", "")

    dt = datetime.strptime(date, "%Y%m%d")

    if dt.weekday() >= 5:
        if verbose:
            print(f"[market-day-check] date={date}, weekend=True")
        return False

    test_tickers = {
        "005930": "삼성전자",
        "000660": "SK하이닉스",
        "035420": "NAVER",
    }

    success_count = 0

    for ticker, name in test_tickers.items():
        try:
            df = stock.get_market_ohlcv_by_date(date, date, ticker)

            has_data = df is not None and not df.empty

            if verbose:
                print(
                    f"[market-day-check] {name}({ticker}) "
                    f"rows={0 if df is None else len(df)}, has_data={has_data}"
                )

            if has_data:
                success_count += 1

        except Exception as e:
            if verbose:
                print(f"[market-day-check] {name}({ticker}) failed: {repr(e)}")

    is_open = success_count > 0

    if verbose:
        print(f"[market-day-check] date={date}, success_count={success_count}, is_open={is_open}")

    return is_open


def is_valid_number_value(value):
    if value is None:
        return False

    value = str(value).strip()

    if value in ("", "None", "null", "undefined", "NaN"):
        return False

    try:
        float(value.replace(",", ""))
        return True
    except ValueError:
        return False

# def dict_from_env() -> Dict[str, Dict[str, str]]:
#     db = {}
#     for k in ("DB_NAME", "DB_USERNAME", "DB_PASSWORD", "DB_HOST", "DB_PORT"):
#         v = os.getenv(k)
#         if v:
#             db[k] = v
#     return {"db": db} if db else {}
#
# db_settings: Dict[str, Any] = dict_from_env()  # 타입 힌트(변수 주석, variable annotation) 문법 > IDE/검사 도구용
#
# conn = psycopg.connect(
#     dbname=db_settings['db']['DB_NAME'],
#     user=db_settings['db']['DB_USERNAME'],
#     password=db_settings['db']['DB_PASSWORD'],
#     host=db_settings['db']['DB_HOST'],
#     port=db_settings['db']['DB_PORT']
# )

# try:
#     sql = """
#     select stock_code
#     from interest_stocks is2
#     group by stock_code
#     having count(stock_code) > 1;
#     """
#     with conn.cursor(row_factory=psycopg.rows.dict_row) as cur: # namedtuple_row는 컬럼명을 속성명으로 쓴다
#         cur.execute(sql, )
#         rows = cur.fetchall()
# except Exception:
#     raise
# finally:
#     conn.close()

# close_list = []
# for i, dick in enumerate(rows):
#     # time.sleep(0.2)  # 200ms 대기
#     ticker = dick['stock_code']
#
#     try:
#         res = requests.post(
#             'https://chickchick.kr/stocks/info',
#             json={"stock_name": str(ticker)},
#             timeout=10
#         )
#         json_data = res.json()
#         # json_data["result"][0]
#         product_code = json_data["result"][0]["data"]["items"][0]["productCode"]
#
#     except Exception as e:
#         print(f"info 요청 실패-2: {str(ticker)} {e}")
#         pass  # 오류
#
#     # 현재 종가 가져오기
#     try:
#         res = requests.post(
#             'https://chickchick.kr/stocks/amount',
#             json={
#                 "product_code": str(product_code)
#             },
#             timeout=5
#         )
#         json_data = res.json()
#         last_close = json_data["result"]["candles"][0]["close"]
#     except Exception as e:
#         print(f"progress-update 요청 실패-3: {e}")
#         pass  # 오류

# conn2 = psycopg.connect(
#     dbname=db_settings['db']['DB_NAME'],
#     user=db_settings['db']['DB_USERNAME'],
#     password=db_settings['db']['DB_PASSWORD'],
#     host=db_settings['db']['DB_HOST'],
#     port=db_settings['db']['DB_PORT']
# )

# try:
#     with conn2.cursor() as cur:
#         sql = "UPDATE interest_stocks SET last_close=%s WHERE stock_code=%s"
#         cur.executemany(sql, close_list)  # 배치
#     conn2.commit()
# except Exception:
#     conn2.rollback()
#     raise
# finally:
#     conn2.close()


# ── Toss API 직접 호출 (헤어핀 제거) ─────────────────────────────────────────
# 자기 웹서버(waitress 12스레드)에 요청을 넣고 그 응답을 기다리는 동안 실제 사용자 요청을 처리할 스레드를 스스로 잡아먹는 구조였다.
# 여기서는 Toss를 곧바로 호출해 그 왕복을 없앤다. URL/헤더는 utils/request_toss_api.py와 동일하게
# 맞춰서 응답 형태(raw Toss JSON)가 그대로 유지되도록 했다(아래 파싱 코드는 바꿀 필요 없음).
_TOSS_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://tossinvest.com",
    "Referer": "https://tossinvest.com/",
    "Cookie": "_browserId=" + uuid.uuid4().hex,   # c-chart가 이 쿠키 없으면 400 (utils/request_toss_api.py 참고)
}
_TOSS_INFO_URL = "https://wts-info-api.tossinvest.com/api/v3/search-all/wts-auto-complete"
_TOSS_AMOUNT_URL = "https://wts-info-api.tossinvest.com/api/v1/c-chart/kr-s/{}/day:1"


def _toss_request_with_retry(fn, *args, retries=3, backoff=1.0, **kwargs):
    # Toss가 짧은 간격의 연속 요청을 속도제한/봇차단으로 끊는 경우가 있어
    # TLS 핸드셰이크 단계에서 SSLError(tlsv1 alert internal error)로 실패한다.
    # 그런 순간적인 차단은 잠깐 쉬었다 재시도하면 풀리는 경우가 많다.
    last_exc = None
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_exc = e
            if attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
    raise last_exc


def _toss_search_stock_info(stock_name_or_ticker):
    res = requests.post(
        _TOSS_INFO_URL,
        json={
            "query": str(stock_name_or_ticker),
            "sections": [
                {"type": "SCREENER"},
                {"type": "PRODUCT", "option": {"addIntegratedSearchResult": True}},
                {"type": "TICS"},
            ],
        },
        headers=_TOSS_HEADERS,
        timeout=10,
    )
    res.raise_for_status()
    return res.json()


def _toss_get_amount(product_code):
    res = requests.get(_TOSS_AMOUNT_URL.format(str(product_code)), headers=_TOSS_HEADERS, timeout=10)
    res.raise_for_status()
    return res.json()


def renew_interest_stocks_close():
    if not is_korean_stock_business_day(verbose=False):
        return

    from app.repository.stocks.stocks import get_interest_stock_list, get_interest_stocks, update_interest_stock_list_close

    start = time.time()   # 시작 시간(초)
    rows = get_interest_stock_list()
    # rows = [{'stock_code':'215790'}]
    nowTime = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
    # today = datetime.now().strftime("%Y%m%d")
    # rows2 = get_interest_stocks(today, "low")  # 이미 get_interest_stock_list 에도 저점이 포함되어 있음
    # rows.extend(rows2)
    print(f'{nowTime} - 🕒 running renew_interest_stocks_close: {len(rows)}')

    close_list = []

    # 2026-10-30: 비공식 wts-info-api가 400으로 막혀 공식 Open API(/api/v1/prices)로 교체.
    # 최대 200종목을 한 번에 조회하므로 종목당 0.2초 대기 루프가 필요 없다. 공식 시세엔 로고가
    # 없어 logo_image_url은 None(UPDATE의 COALESCE가 기존 DB 값을 유지).
    tickers = [str(r['stock_code']) for r in rows]
    try:
        prices = get_last_prices(tickers)
    except Exception as e:
        print(f"renew_interest_stocks_close [prices 요청 실패]: {e}")
        prices = {}

    for ticker in tickers:
        last_close = prices.get(ticker)   # 거래정지 등으로 응답에 없으면 건너뜀
        if last_close is None:
            continue
        if is_valid_number_value(last_close):
            close_list.append((str(int(last_close)) if float(last_close).is_integer() else str(last_close),
                               None, None, ticker))    # 순서: (close, category, logo, 키)
        else:
            print(f"invalid last_close: {ticker} last_close={last_close!r}")

    if len(close_list) > 0:
        update_interest_stock_list_close(close_list)

    end = time.time()     # 끝 시간(초)
    elapsed = end - start

    hours, remainder = divmod(int(elapsed), 3600)
    minutes, seconds = divmod(remainder, 60)

    # if elapsed > 20:
    #     print(f"총 소요 시간: {hours}시간 {minutes}분 {seconds}초")
    # print(f'complete renew_interest_stocks_close: {len(rows)}')
    logger.info(f'Complete : renew_interest_stocks_close: {len(rows)}, 총 소요 시간: {hours}시간 {minutes}분 {seconds}초')


def verify_low_stock_data():
    from app.repository.stocks.stocks import get_today_low_stocks, get_today_interest_stocks, update_stocks_break_away

    stocks = get_today_low_stocks()
    stocks2 = get_today_interest_stocks()
    combined = stocks + stocks2

    for stock in combined:
        try:
            update_stocks_break_away(stock)
        except Exception as e:
            print(f"Failed to update stock {stock}: {e}")


# 하루에 한번 토스 product_code 갱신
def update_product_code():
    from app.repository.stocks.stocks import get_stock_list, update_stocks_product_code
    stocks = get_stock_list("kor")

    # 2026-10-30: 비공식 검색 API가 막혀서(400) productCode를 검색으로 얻지 못한다. KRX 종목의
    # productCode는 'A'+6자리 종목코드라(실측: A000660, A489790 …) API 없이 만든다. AutoSales의
    # job들이 이 값을 DB에서 읽어 None 여부만 확인하고 6자리로 되돌려 쓴다.
    for stock in stocks:
        try:
            stock_code = stock.get('stock_code')
            if not stock_code:
                continue

            update_stocks_product_code(stock_code, f"A{stock_code}")
        except Exception as e:
            print(f"Failed to update stock {stock}: {e}")


# if __name__ == '__main__':
    # renew_interest_stocks_close()
    # update_product_code()