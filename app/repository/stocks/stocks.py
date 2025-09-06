from typing import List

from config.db_connect import db_transaction
import psycopg


@db_transaction
def update_stock_list(stocks: List["StockDTO"], conn=None, batch_size: int = 500) -> None:
    sql = """
    INSERT INTO stocks (
        created_at, nation, stock_code, stock_name, sector_code, stock_market
    )
    VALUES (now(), %s, %s, %s, %s, %s)
    ON CONFLICT (stock_code, (created_at::date))
    DO UPDATE SET
        nation       = COALESCE(EXCLUDED.nation, stocks.nation),
        stock_code   = COALESCE(EXCLUDED.stock_code, stocks.stock_code),
        stock_name   = COALESCE(EXCLUDED.stock_name, stocks.stock_name),
        sector_code  = COALESCE(EXCLUDED.sector_code, stocks.sector_code);
        stock_market = COALESCE(EXCLUDED.stock_market, stocks.stock_market);
    """

    with conn.cursor() as cur:
        for i in range(0, len(stocks), batch_size):
            batch = stocks[i:i + batch_size]
            rows = [(s.nation, s.stock_code, s.stock_name, s.sector_code, s.stock_market) for s in batch]
            cur.executemany(sql, rows)

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
def merge_daily_interest_stocks(stock: "StockDTO", conn=None) -> int:
    with conn.cursor() as cur:
        sql = """
        INSERT INTO interest_stocks (
            created_at, updated_at, nation, stock_code, stock_name, 
            pred_price_change_3d_pct, yesterday_close, current_price, today_price_change_pct,
            avg5d_trading_value, current_trading_value, trading_value_change_pct,
            image_url, logo_image_url
        )
        VALUES (
            now(), now(), %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s
        )
        -- ON CONFLICT ON CONSTRAINT stocks_code_daily
        ON CONFLICT (stock_code, (created_at::date))
        DO UPDATE SET
            updated_at               = now(),
            nation                   = COALESCE(EXCLUDED.nation, stocks.nation),
            stock_code               = COALESCE(EXCLUDED.stock_code, stocks.stock_code),
            stock_name               = COALESCE(EXCLUDED.stock_name, stocks.stock_name),
            pred_price_change_3d_pct = COALESCE(EXCLUDED.pred_price_change_3d_pct, stocks.pred_price_change_3d_pct),
            yesterday_close          = COALESCE(EXCLUDED.yesterday_close, stocks.yesterday_close),
            current_price            = COALESCE(EXCLUDED.current_price, stocks.current_price),
            today_price_change_pct   = COALESCE(EXCLUDED.today_price_change_pct, stocks.today_price_change_pct),
            avg5d_trading_value      = COALESCE(EXCLUDED.avg5d_trading_value, stocks.avg5d_trading_value),
            current_trading_value    = COALESCE(EXCLUDED.current_trading_value, stocks.current_trading_value),
            trading_value_change_pct = COALESCE(EXCLUDED.trading_value_change_pct, stocks.trading_value_change_pct),
            image_url                = COALESCE(EXCLUDED.image_url, stocks.image_url),
            logo_image_url           = COALESCE(EXCLUDED.image_url, stocks.logo_image_url)
        RETURNING id;
        """
        cur.execute(
            sql,
            (
                stock.nation, stock.stock_code, stock.stock_name, stock.pred_price_change_3d_pct,
                stock.yesterday_close, stock.current_price, stock.today_price_change_pct,
                stock.avg5d_trading_value, stock.current_trading_value,
                stock.trading_value_change_pct, stock.image_url, stock.logo_image_url
            )
        )
        row = cur.fetchone()
        return row[0] if row else None


@db_transaction
def get_interest_stocks(date: str, conn=None):
    sql = """
    SELECT *
    FROM interest_stocks
    WHERE created_at::date = %s
    ORDER BY current_trading_value::numeric DESC, today_price_change_pct::numeric DESC;
    """
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur: # namedtuple_row는 컬럼명을 속성명으로 쓴다
        cur.execute(sql, (date,))
        rows = cur.fetchall()
    return rows
