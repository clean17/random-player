from typing import Dict, Any
import psycopg
import psycopg_pool
import os
import requests
import time
from datetime import datetime, time as dtime

from pathlib import Path
import sys

from utils.wsgi_midleware import logger

sys.path.append(str(Path(__file__).resolve().parents[1]))  # project_root


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


def renew_interest_stocks_close():
    from app.repository.stocks.stocks import get_interest_stock_list, update_interest_stock_list_close

    start = time.time()   # 시작 시간(초)
    rows = get_interest_stock_list()
    # rows = [{'stock_code':'215790'}]
    nowTime = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
    print(f'{nowTime} - 🕒 running renew_interest_stocks_close: {len(rows)}')

    close_list = []

    for i, row in enumerate(rows):
        time.sleep(0.05)  # 50ms 대기
        ticker = row['stock_code']

        try:
            res = requests.post(
                'https://chickchick.kr/stocks/info',
                json={"stock_name": str(ticker)},
                timeout=10
            )
            json_data = res.json() or {}
            result = json_data["result"]

            # 거래정지는 데이터를 주지 않는다
            if len(result) == 0:
                continue

            product_code = json_data["result"][0]["data"]["items"][0]["productCode"]
            product_name = json_data["result"][0]["data"]["items"][0]["productName"]
            logo_image_url = json_data["result"][0]["data"]["items"][0]["logoImageUrl"]
        except Exception as e:
            print(f"renew_interest_stocks_close [info 요청 실패1]: {str(ticker)} {str(product_name)} {e}")
            continue  # 오류


        # 현재 종가 가져오기
        try:
            res4 = requests.post(
                'https://chickchick.kr/stocks/amount',
                json={"product_code": str(product_code)},
                timeout=10
            )
            json_data = res4.json() or {}
            last_close = json_data["result"]["candles"][0]["close"]
        except Exception as e:
            print(f"renew_interest_stocks_close [info 요청 실패4]: {str(ticker)} {str(product_name)} {e}")
            continue  # 오류

        # print(f'{i+1}/{len(rows)} ticker : {ticker}, close : {last_close}')
        if is_valid_number_value(last_close):
            # close_list.append((str(last_close), category, logo_image_url, ticker))    # 순서: (값, 키)
            close_list.append((str(last_close).replace(",", ""), None, logo_image_url, ticker))    # 순서: (값, 키)
        else:
            print(f"invalid last_close: {ticker} {product_name} last_close={last_close!r}")
            continue
        # update_interest_stock_list_close(close_list)   # 급하게 데이터 넣을 때
        # close_list.clear()

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
    from app.repository.stocks.stocks import get_today_low_stocks, update_stocks_low_away

    stocks = get_today_low_stocks()
    for stock in stocks:
        try:
            update_stocks_low_away(stock)
        except Exception as e:
            print(f"Failed to update stock {stock}: {e}")


# if __name__ == '__main__':
#     renew_interest_stocks_close()