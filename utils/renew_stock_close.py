from typing import Dict, Any
import psycopg
import psycopg_pool
import os
import requests
import time

from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))  # project_root

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
#             'https://chickchick.shop/func/stocks/info',
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
#             'https://chickchick.shop/func/stocks/amount',
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
    rows = get_interest_stock_list()

    close_list = []
    for i, dick in enumerate(rows):
        # time.sleep(0.2)  # 200ms 대기
        ticker = dick['stock_code']

        try:
            res = requests.post(
                'https://chickchick.shop/func/stocks/info',
                json={"stock_name": str(ticker)},
                timeout=10
            )
            json_data = res.json()
            result = json_data["result"]

            # 거래정지는 데이터를 주지 않는다
            if len(result) == 0:
                continue

            product_code = json_data["result"][0]["data"]["items"][0]["productCode"]

        except Exception as e:
            print(f"renew_interest_stocks_close [info 요청 실패]: {str(ticker)} {e}")
            pass  # 오류

        # 현재 종가 가져오기
        try:
            res = requests.post(
                'https://chickchick.shop/func/stocks/amount',
                json={
                    "product_code": str(product_code)
                },
                timeout=10
            )
            json_data = res.json()
            last_close = json_data["result"]["candles"][0]["close"]
        except Exception as e:
            print(f"progress-update 요청 실패-3: {e}")
            pass  # 오류

        # print(f'{i+1}/{len(rows)} ticker : {ticker}, close : {last_close}')
        close_list.append((last_close, ticker))    # 순서: (값, 키)

    if len(close_list) > 0:
        update_interest_stock_list_close(close_list)