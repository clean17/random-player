from typing import List, Sequence, Tuple
from config.db_connect import db_transaction
import psycopg


@db_transaction
def update_stock_list(stocks: List["StockDTO"], conn=None, batch_size: int = 500) -> None:
    sql = """
    INSERT INTO stocks (
        created_at, nation, stock_code, stock_name, sector_code, stock_market
    )
    VALUES (now(), %s, %s, %s, %s, %s)
    ON CONFLICT (stock_code)
    DO UPDATE SET
        nation       = COALESCE(EXCLUDED.nation,       stocks.nation),
        stock_name   = COALESCE(EXCLUDED.stock_name,   stocks.stock_name),
        sector_code  = COALESCE(EXCLUDED.sector_code,  stocks.sector_code),
        stock_market = COALESCE(EXCLUDED.stock_market, stocks.stock_market),
        updated_at   = now();
    """

    with conn.cursor() as cur:
        for i in range(0, len(stocks), batch_size):
            batch = stocks[i:i + batch_size]
            rows = [(s.nation, s.stock_code, s.stock_name, s.sector_code, s.stock_market) for s in batch]
            cur.executemany(sql, rows)

@db_transaction
def update_interest_stock_list_close(rows: Sequence[Tuple[float, str]], conn=None, batch_size: int = 500) -> None:
    sql = """
        UPDATE interest_stocks SET last_close = %s, updated_at = now() WHERE stock_code = %s;
    """

    with conn.cursor() as cur:
        # 배치로 쪼개서 보내기 (너무 큰 executemany 방지)
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            cur.executemany(sql, batch)  # (값, 키) 순서 주의

@db_transaction
def get_stock_list(nation: str, conn=None):
    sql = """
    SELECT stock_code, stock_name, sector_code, stock_market FROM stocks 
    WHERE nation = %s
    ORDER BY id;
    """
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur: # namedtuple_row는 컬럼명을 속성명으로 쓴다
        cur.execute(sql, (nation,))
        rows = cur.fetchall()
    return rows

@db_transaction
def get_interest_stock_list(conn=None):
    sql = """
    select stock_code
    from interest_stocks is2 
    group by stock_code
    having count(stock_code) > 1;
    """
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur: # namedtuple_row는 컬럼명을 속성명으로 쓴다
        cur.execute(sql, )
        rows = cur.fetchall()
    return rows

@db_transaction
def merge_daily_interest_stocks(stock: "StockDTO", conn=None) -> int:
    with conn.cursor() as cur:
        sql = """
        INSERT INTO interest_stocks (
            created_at, updated_at, nation, stock_code, stock_name, 
            pred_price_change_3d_pct, yesterday_close, current_price, today_price_change_pct,
            avg5d_trading_value, current_trading_value, trading_value_change_pct,
            image_url, logo_image_url, market_value, category, target, last_close
        )
        VALUES (
            now(), now(), %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s, %s, %s
        )
        -- ON CONFLICT ON CONSTRAINT stocks_code_daily
        ON CONFLICT (stock_code, (created_at::date))
        DO UPDATE SET
            updated_at               = now(),
            nation                   = COALESCE(EXCLUDED.nation,                   interest_stocks.nation),
            stock_name               = COALESCE(EXCLUDED.stock_name,               interest_stocks.stock_name),
            pred_price_change_3d_pct = COALESCE(EXCLUDED.pred_price_change_3d_pct, interest_stocks.pred_price_change_3d_pct),
            yesterday_close          = COALESCE(EXCLUDED.yesterday_close,          interest_stocks.yesterday_close),
            current_price            = COALESCE(EXCLUDED.current_price,            interest_stocks.current_price),
            today_price_change_pct   = COALESCE(EXCLUDED.today_price_change_pct,   interest_stocks.today_price_change_pct),
            avg5d_trading_value      = COALESCE(EXCLUDED.avg5d_trading_value,      interest_stocks.avg5d_trading_value),
            current_trading_value    = COALESCE(EXCLUDED.current_trading_value,    interest_stocks.current_trading_value),
            trading_value_change_pct = COALESCE(EXCLUDED.trading_value_change_pct, interest_stocks.trading_value_change_pct),
            image_url                = COALESCE(EXCLUDED.image_url,                interest_stocks.image_url),
            logo_image_url           = COALESCE(EXCLUDED.logo_image_url,           interest_stocks.logo_image_url),
            market_value             = COALESCE(EXCLUDED.market_value,             interest_stocks.market_value),
            category                 = COALESCE(EXCLUDED.category,                 interest_stocks.category),
            target                   = COALESCE(EXCLUDED.target,                   interest_stocks.target),
            last_close               = COALESCE(EXCLUDED.last_close,               interest_stocks.last_close)
        RETURNING id;
        """
        cur.execute(
            sql,
            (
                stock.nation, stock.stock_code, stock.stock_name, stock.pred_price_change_3d_pct,
                stock.yesterday_close, stock.current_price, stock.today_price_change_pct,
                stock.avg5d_trading_value, stock.current_trading_value,
                stock.trading_value_change_pct, stock.image_url, stock.logo_image_url, stock.market_value,
                stock.category, stock.target, stock.last_close
            )
        )
        row = cur.fetchone()
        return row[0] if row else None


# 오늘의 실시간 등락
@db_transaction
def get_interest_stocks(date: str, conn=None):
    sql = """
    SELECT *
    FROM interest_stocks
    WHERE created_at::date = %s
    AND today_price_change_pct::float >= 4
    AND current_trading_value::numeric > 5_000_000_000
    ORDER BY today_price_change_pct::numeric DESC, current_trading_value::numeric DESC;
    """
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur: # namedtuple_row는 컬럼명을 속성명으로 쓴다
        cur.execute(sql, (date,))
        rows = cur.fetchall()
    return rows


@db_transaction
def get_interest_stocks_info(date: str, conn=None):
    sql = """
select row_number() over (
    order by count desc
    , REGEXP_REPLACE(avg_change_pct, '%%', '', 'g')::numeric desc
    , REGEXP_REPLACE(total_rate_of_increase, '%%', '', 'g')::numeric desc
    ) as rn
, b.* 
, (select image_url from interest_stocks is3 where is3.id = b.id)
, (select category from interest_stocks is3 where is3.id = b.id)
from (
select stock_code
  , stock_name
  , count(stock_code)
  , to_char(min(current_price::numeric), 'FM999,999,999') as min
  , to_char(max(last_close::numeric), 'FM999,999,999') as last
  , ROUND(
      AVG(
        COALESCE(
          NULLIF(REGEXP_REPLACE(today_price_change_pct, '%%', '', 'g'), '')::numeric, 0)
       )
    , 1)||'%%' AS avg_change_pct  
  , ROUND(100.0 * (coalesce(max(last_close::numeric), 0) - MIN(current_price::numeric))
       / NULLIF(MIN(current_price::numeric), 0),1)||'%%' AS total_rate_of_increase
  , ROUND(100.0 * (coalesce(max(last_close::numeric), 0) - MIN(current_price::numeric))
       / NULLIF(MIN(current_price::numeric), 0)  / count(stock_code), 1)||'%%' as increase_per_day
  , case when max(market_value::numeric) >= 1_000_000_000_000
  		 then ROUND(max(market_value::numeric)/1_000_000_000_000, 1)||'조'
         else ROUND(max(market_value::numeric)/100_000_000)||'억'
         end as market_value
  , ROUND(avg(current_trading_value::numeric)/100000000)||'억' as avg_trading_value
  , min(created_at)::date as first_date
  , max(created_at)::date as last_date
  , max(id) as id
from interest_stocks is2 
where 1=1
and is2.market_value::numeric > 50_000_000_000
and is2.current_trading_value::numeric > 7_000_000_000
and is2.current_trading_value::numeric < 500_000_000_000
--and is2.created_at >= NOW() - INTERVAL '1 month'
--and is2.created_at >= CURRENT_DATE - make_interval(days => (CURRENT_DATE - '날짜'::date + 1))
and is2.created_at >= %s::date
and today_price_change_pct is not null
group by stock_code, stock_name
having count(stock_code) > 1
--and count(stock_code) < 6
and max(created_at) >= (CURRENT_DATE - INTERVAL '7 days') -- x일 전부터 등록된 것
order by count(stock_code) desc, max(created_at) desc
) as b
where REGEXP_REPLACE(avg_change_pct, '%%', '', 'g')::numeric > 5.7
and REGEXP_REPLACE(total_rate_of_increase, '%%', '', 'g')::numeric > 10
and REGEXP_REPLACE(increase_per_day, '%%', '', 'g')::numeric > 3.5
and REGEXP_REPLACE(increase_per_day, '%%', '', 'g')::numeric < 10
;
    """
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur: # namedtuple_row는 컬럼명을 속성명으로 쓴다
        cur.execute(sql, (date,))
        # cur.execute(sql, )
        rows = cur.fetchall()
    return rows

@db_transaction
def get_interest_low_stocks(date: str, conn=None):
    sql = """
    SELECT id, image_url, stock_name, stock_code, category, created_at
    , yesterday_close, current_price, today_price_change_pct
    , avg5d_trading_value, current_trading_value, trading_value_change_pct
    , case when market_value::numeric >= 1_000_000_000_000
      		 then ROUND(market_value::numeric/1_000_000_000_000, 1)||'조'
             else ROUND(market_value::numeric/100_000_000)||'억'
             end as market_value  
    FROM interest_stocks
    WHERE created_at::date = %s
    AND today_price_change_pct::numeric > 3.8
    AND target = 'low'
    ORDER BY today_price_change_pct::numeric DESC;
    """
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur: # namedtuple_row는 컬럼명을 속성명으로 쓴다
        cur.execute(sql, (date,))
        rows = cur.fetchall()
    return rows

@db_transaction
def delete_delisted_stock(conn=None):
    sql = """
    delete from stocks where updated_at::date <> now()::date;
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        deleted_count = cur.rowcount   # ← 삭제된 행 수
    return deleted_count