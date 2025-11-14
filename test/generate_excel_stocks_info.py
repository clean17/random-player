from typing import Dict, Any

from datetime import datetime
import pandas as pd
import psycopg
import os

def dict_from_env() -> Dict[str, Dict[str, str]]:
    db = {}
    for k in ("DB_NAME", "DB_USERNAME", "DB_PASSWORD", "DB_HOST", "DB_PORT"):
        v = os.getenv(k)
        if v:
            db[k] = v
    return {"db": db} if db else {}

db_settings: Dict[str, Any] = dict_from_env()  # 타입 힌트(변수 주석, variable annotation) 문법 > IDE/검사 도구용

conn = psycopg.connect(
    dbname=db_settings['db']['DB_NAME'],
    user=db_settings['db']['DB_USERNAME'],
    password=db_settings['db']['DB_PASSWORD'],
    host=db_settings['db']['DB_HOST'],
    port=db_settings['db']['DB_PORT']
)




def autofit_columns(ws):
    for col in ws.columns:
        max_len = 0
        col_letter = col[0].column_letter
        for cell in col:
            try:
                v = str(cell.value) if cell.value is not None else ""
                max_len = max(max_len, len(v))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max_len + 8, 60)

def main():
    # 파일명: result_YYYYMMDD_HHMMSS.xlsx
    # out_name = f"상승종목정리_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    out_name = f"상승종목정리_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    # DB 연결
    try:
        sql = """
        select row_number() over (
            order by 상승_카운트 desc
            , REGEXP_REPLACE(평균_변동률, '%', '', 'g')::numeric desc
            , REGEXP_REPLACE(전체_상승률, '%', '', 'g')::numeric desc
            ) as 순서
        , b.* 
        from (
        select stock_code as 종목코드
          , stock_name as 종목명
          , count(stock_code) as 상승_카운트
          , to_char(min(current_price::numeric), 'FM999,999,999') as 시작가
        --  , max(current_price)
          , to_char(min(current_price::numeric), 'FM999,999,999') as 현재가
          , ROUND(
              AVG(
                COALESCE(
                  NULLIF(REGEXP_REPLACE(today_price_change_pct, '%', '', 'g'), '')::numeric, 0)
               )
            , 1)||'%' AS 평균_변동률  
          , ROUND(100.0 * (coalesce(max(last_close)::numeric, 0) - MIN(current_price)::numeric)
               / NULLIF(MIN(current_price)::numeric, 0),1)||'%' AS 전체_상승률
          , case when max(market_value)::numeric >= 1000000000000
          		 then ROUND(max(market_value)::numeric/1000000000000, 1)||'조'
                 else ROUND(max(market_value)::numeric/100000000)||'억'
                 end as 시가총액
          , ROUND(avg(current_trading_value::numeric)/100000000)||'억' as 평균_거래대금
          , min(created_at)::date as 처음_상승일자
          , max(created_at)::date as 마지막_상승일자
        from interest_stocks is2 
        where 1=1
        --and is2.created_at >= NOW() - INTERVAL '1 month'
        and is2.created_at >= (CURRENT_DATE - INTERVAL '14 days')
        and today_price_change_pct is not null
        group by stock_code, stock_name
        having count(stock_code) > 1
        --and count(stock_code) < 6
        and max(created_at) >= (CURRENT_DATE - INTERVAL '5 days') -- x일 전부터 등록된 것
        order by count(stock_code) desc, max(created_at) desc
        ) as b
        where REGEXP_REPLACE(평균_변동률, '%', '', 'g')::numeric > 6
        and REGEXP_REPLACE(전체_상승률, '%', '', 'g')::numeric > 5
        """
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur: # namedtuple_row는 컬럼명을 속성명으로 쓴다
            cur.execute(sql, )
            cols = [desc.name for desc in cur.description]
            rows = cur.fetchall()
    except Exception:
        raise
    finally:
        conn.close()

    # DataFrame으로 변환
    df = pd.DataFrame(rows, columns=cols)

    # 엑셀 저장
    with pd.ExcelWriter(out_name, engine="openpyxl") as writer:
        sheet = "result"
        df.to_excel(writer, index=False, sheet_name=sheet)

        # 오토핏(대략)
        ws = writer.sheets[sheet]
        autofit_columns(ws)

    print(f"Saved: {out_name}")

if __name__ == "__main__":
    main()