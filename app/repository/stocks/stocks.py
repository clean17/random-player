from config.db_connect import db_transaction
import psycopg

@db_transaction
def merge_daily_interest_stocks(stock: "StockDTO", conn=None) -> int:
    with conn.cursor() as cur:
        sql = """
        INSERT INTO stocks (
            created_at, nation, stock_code, stock_name, pred_price_change_3d_pct,
            yesterday_close, current_price, today_price_change_pct,
            avg5d_trading_value, current_trading_value, trading_value_change_pct,
            image_url, updated_at
        )
        VALUES (
            now(), %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, now()
        )
        -- ON CONFLICT ON CONSTRAINT stocks_code_daily
        ON CONFLICT (stock_code, (created_at::date))
        DO UPDATE SET
            nation                     = EXCLUDED.nation,
            stock_code                 = EXCLUDED.stock_code,
            stock_name                 = EXCLUDED.stock_name,
            pred_price_change_3d_pct   = EXCLUDED.pred_price_change_3d_pct,
            yesterday_close            = EXCLUDED.yesterday_close,
            current_price              = EXCLUDED.current_price,
            today_price_change_pct     = EXCLUDED.today_price_change_pct,
            avg5d_trading_value        = EXCLUDED.avg5d_trading_value,
            current_trading_value      = EXCLUDED.current_trading_value,
            trading_value_change_pct   = EXCLUDED.trading_value_change_pct,
            image_url                  = EXCLUDED.image_url,
            updated_at                 = now()
        RETURNING id;
        """
        cur.execute(
            sql,
            (
                stock.nation, stock.stock_code, stock.stock_name, stock.pred_price_change_3d_pct,
                stock.yesterday_close, stock.current_price, stock.today_price_change_pct,
                stock.avg5d_trading_value, stock.current_trading_value,
                stock.trading_value_change_pct, stock.image_url
            )
        )
        row = cur.fetchone()
        return row[0] if row else None


@db_transaction
def get_interest_stocks(date: str, conn=None):
    sql = """
    SELECT *
    FROM stocks
    WHERE created_at::date = %s
    ORDER BY today_price_change_pct::numeric DESC, current_trading_value::numeric DESC;
    """
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur: # namedtuple_row는 컬럼명을 속성명으로 쓴다
        cur.execute(sql, (date,))
        rows = cur.fetchall()
    return rows
