from typing import List, Sequence, Tuple
from config.db_connect import db_transaction
import psycopg
from utils.wsgi_midleware import logger


# 매일 아침 국장 종목 갱신
@db_transaction
def update_stock_list(stocks: List["StockDTO"], conn=None, batch_size: int = 500) -> None:
    sql = """
    INSERT INTO stocks (
        created_at, nation, stock_code, stock_name, sector_code, category, stock_market
    )
    VALUES (now(), %s, %s, %s, %s, %s, %s)
    ON CONFLICT (stock_code)
    DO UPDATE SET
        nation       = COALESCE(EXCLUDED.nation,       stocks.nation),
        stock_name   = COALESCE(EXCLUDED.stock_name,   stocks.stock_name),
        sector_code  = COALESCE(EXCLUDED.sector_code,  stocks.sector_code),
        stock_market = COALESCE(EXCLUDED.stock_market, stocks.stock_market),
        category     = COALESCE(EXCLUDED.category,     stocks.category),
        updated_at   = now();
    """

    with conn.cursor() as cur:
        for i in range(0, len(stocks), batch_size):
            batch = stocks[i:i + batch_size]
            rows = [(s.nation, s.stock_code, s.stock_name, s.sector_code, s.category, s.stock_market) for s in batch]
            cur.executemany(sql, rows)

# 매일 아침 국장 종목 갱신
@db_transaction
def delete_delisted_stock(conn=None):
    sql = """
    --delete from stocks where updated_at::date <> now()::date;
    update stocks
    set
        flag = FALSE
    where updated_at::date <> now()::date;
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        deleted_count = cur.rowcount   # ← 삭제된 행 수
    return deleted_count


# 30분마다 종가, 로고를 수정
@db_transaction
def update_interest_stock_list_close(rows: Sequence[Tuple[float, str, str, str]], conn=None, batch_size: int = 500) -> None:
    sql = """
        UPDATE stocks 
        SET 
            close          = COALESCE(%s, close),
            category       = COALESCE(%s, category),
            logo_image_url = COALESCE(%s, logo_image_url),
            updated_at = now() 
        WHERE stock_code = %s;
    """

    with conn.cursor() as cur:
        # 배치로 쪼개서 보내기 (너무 큰 executemany 방지)
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            cur.executemany(sql, batch)  # (값, 키) 순서 주의


# 국장/미장 모든 종목 조회
@db_transaction
def get_stock_list(nation: str, conn=None):
    sql = """
    SELECT stock_code
         , stock_name
         , sector_code
         , stock_market
         , product_code
    FROM stocks 
    WHERE nation = %s
    and flag = True
    ORDER BY id;
    """
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur: # namedtuple_row는 컬럼명을 속성명으로 쓴다
        cur.execute(sql, (nation,))
        rows = cur.fetchall()
    return rows


# 종가를 갱신할 때 조회
@db_transaction
def get_interest_stock_list(conn=None):
    sql = """
    select stock_code
    from interest_stocks is2 
    where updated_at > now() - interval '30 days'
    group by stock_code
    having count(stock_code) >= 1;
    """
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur: # namedtuple_row는 컬럼명을 속성명으로 쓴다
        cur.execute(sql, )
        rows = cur.fetchall()
    return rows


@db_transaction
def get_favorite_stocks(user_id, conn=None) -> int:
    sql = """
    select stock_code from favorite_stocks 
    where user_id = %s 
    and flag = True;
    """
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur: # namedtuple_row는 컬럼명을 속성명으로 쓴다
        cur.execute(sql, (user_id,))
        rows = cur.fetchall()
    return rows


@db_transaction
def upsert_favorite_stocks(stock: "StockDTO", conn=None) -> int:
    with conn.cursor() as cur:
        sql = """
        INSERT INTO favorite_stocks (
            created_at, updated_at, user_id, stock_code, flag
        )
        VALUES (
            now(), now(), %s, %s, True
        )
        ON CONFLICT (stock_code, user_id)
        DO UPDATE SET
            updated_at               = now(),
            flag                     = NOT favorite_stocks.flag
        RETURNING id;
        """
        cur.execute(
            sql,
            (
                stock.user_id, stock.stock_code
            )
        )
        row = cur.fetchone()
        return row[0] if row else None


# 관심 종목 insert, EXCLUDED: 새로 들어온 값
@db_transaction
def merge_daily_interest_stocks(stock: "StockDTO", conn=None) -> int:
    with conn.cursor() as cur:
        sql = """
        INSERT INTO interest_stocks (
            created_at, updated_at, nation, stock_code, stock_name, 
            pred_price_change_3d_pct, yesterday_close, current_price, today_price_change_pct,
            avg5d_trading_value, current_trading_value, trading_value_change_pct,
            graph_file, market_value, target
        )
        VALUES (
            now(), now(), %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s
        )
        -- ON CONFLICT ON CONSTRAINT stocks_code_daily
        ON CONFLICT (stock_code, target, (created_at::date))
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
            graph_file               = COALESCE(EXCLUDED.graph_file,               interest_stocks.graph_file),
            market_value             = COALESCE(EXCLUDED.market_value,             interest_stocks.market_value)
            --target                   = COALESCE(EXCLUDED.target,                   interest_stocks.target)
        RETURNING id;
        """
        cur.execute(
            sql,
            (
                stock.nation, stock.stock_code, stock.stock_name, stock.pred_price_change_3d_pct,
                stock.yesterday_close, stock.current_price, stock.today_price_change_pct,
                stock.avg5d_trading_value, stock.current_trading_value,
                stock.trading_value_change_pct, stock.graph_file, stock.market_value,
                stock.target
            )
        )
        row = cur.fetchone()
        return row[0] if row else None


# 상승주 그래프만 갱신
@db_transaction
def update_interest_stock_graph(stock: "StockDTO", conn=None) -> None:
    sql = """
        UPDATE stocks 
        SET 
            graph_file  = COALESCE(%s, graph_file),
            updated_at = now() 
        WHERE stock_code = %s 
        RETURNING id;
    """

    with conn.cursor() as cur:
        cur.execute(
            sql,
            (
                stock.graph_file, stock.stock_code
            )
        )
        row = cur.fetchone()
        return row[0] if row else None


# 저점 그래프만 갱신 (매수 시점으로부터 2주 동안)
@db_transaction
def update_low_stock_graph(stock: "StockDTO", conn=None) -> None:
    sql = """
        UPDATE interest_stocks 
        SET 
            graph_file  = COALESCE(%s, graph_file),
            updated_at = now() 
        WHERE stock_code = %s 
          AND created_at::date = %s
          AND target like 'low%%'
        RETURNING id;
    """

    with conn.cursor() as cur:
        cur.execute(
            sql,
            (
                stock.graph_file, stock.stock_code, stock.created_at
            )
        )
        row = cur.fetchone()
        return row[0] if row else None

# 실시간, 저점 데이터 조회
@db_transaction
def get_interest_stocks(date: str, endDate: str, mode: str = "normal", conn=None):
    base_sql = """
    SELECT 
        --row_number() over (order by i.id) as rn 
        i.id
        , i.stock_code
        , i.stock_name
        , s.category        
        , i.yesterday_close
        , i.current_price
        , s.close
        , i.today_price_change_pct
        , i.avg5d_trading_value
        , i.current_trading_value
        , i.trading_value_change_pct
        , i.pred_price_change_3d_pct
        , i.graph_file
        , i.market_value
        , i.created_at
        , i.updated_at              
        , s.logo_image_url
        , s.product_code
        , i.target
    FROM interest_stocks i
    JOIN stocks s ON i.stock_code = s.stock_code
    WHERE i.created_at::date >= %s
      AND i.created_at::date <= %s
      AND s.flag = TRUE
    """

    params = [date, endDate]

    if mode == "normal":
        base_sql += """
          AND i.today_price_change_pct::float >= 4
          AND i.current_trading_value::numeric > 5_000_000_000
          AND i.target = 'interest'
        ORDER BY i.today_price_change_pct::numeric DESC,
                 i.current_trading_value::numeric DESC
        """

    elif mode == "low":
        base_sql += """
          AND i.today_price_change_pct::numeric > 3.3
          AND i.target LIKE 'low%%'
        ORDER BY i.created_at::date, i.today_price_change_pct::numeric DESC
        """

    else:
        raise ValueError(f"Invalid mode: {mode}")

    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:   # namedtuple_row는 컬럼명을 속성명으로 쓴다
        cur.execute(base_sql, params)
        rows = cur.fetchall()

    return rows


# 최근 상승주 검색
@db_transaction
def get_interest_stocks_info(date: str, endDate: str, user_id: int = None, conn=None):
    # user_id 있을 때만: favorite join + current_trading_value 컬럼 추가
    favorite_join = ""
    target_condition = ""
    fire_condition = ""
    trading_value_condition = ""
    params = []

    if user_id is not None:
        favorite_join = """
            join favorite_stocks f on f.stock_code = s.stock_code and f.flag = true and f.user_id = %s
        """
        params = [user_id, date, endDate]
    else:
        trading_value_condition = """
            and i.current_trading_value::numeric > 4_000_000_000 -- 최소 거래대금 수정 40억
        """
        target_condition = """
            and i.target = 'interest'
        """
        fire_condition = """
            where REGEXP_REPLACE(avg_change_pct, '%%', '', 'g')::numeric > 5
            and REGEXP_REPLACE(total_rate_of_increase, '%%', '', 'g')::numeric > 8.5
            and REGEXP_REPLACE(increase_per_day, '%%', '', 'g')::numeric < 20
            and REGEXP_REPLACE(increase_per_day, '%%', '', 'g')::numeric > 3.8
            and min < close
        """
        params = [date, endDate]

    sql = f"""
    select 
        row_number() over (
            order by count desc
            , REGEXP_REPLACE(avg_change_pct, '%%', '', 'g')::numeric desc
            , REGEXP_REPLACE(total_rate_of_increase, '%%', '', 'g')::numeric desc
        ) as rn
        , b.id
        , b.stock_name
        , b.stock_code
        , b.category
        , b.count
        , b.min
        , b.last
        , b.close
        , b.avg_change_pct
        , b.total_rate_of_increase
        , b.increase_per_day
        , b.market_value
        , b.avg_trading_value
        , last_i.last_trading_value_num as current_trading_value
        , b.first_date
        , b.last_date
        , b.logo_image_url
        , coalesce(b.s_graph_file, last_i.graph_file) as graph_file
    from (
        select 
          max(i.id) as id
          , i.stock_code
          , I.stock_name
          , count(i.stock_code)
          , to_char(min(current_price::numeric), 'FM999,999,999') as min
          , to_char(
              case 
                when max(i.created_at)::date <> CURRENT_DATE 
                  then max(i.current_price::numeric)
                else s.close::numeric
              end, 'FM999,999,999'
            ) as last
          , ROUND(
              AVG(
                COALESCE(
                  NULLIF(REGEXP_REPLACE(i.today_price_change_pct, '%%', '', 'g'), '')::numeric, 0)
               )
            , 1)||'%%' AS avg_change_pct  
          , ROUND(
              100.0 * (
                case when max(i.created_at)::date <> CURRENT_DATE 
                     then max(i.current_price::numeric)
                     else s.close::numeric
                end 
                - MIN(current_price::numeric)
                ) / NULLIF(MIN(current_price::numeric), 0)
            , 1)||'%%' AS total_rate_of_increase
          , ROUND(
              100.0 * (
                case when max(i.created_at)::date <> CURRENT_DATE 
                     then max(i.current_price::numeric)
                     else s.close::numeric
                end 
                - MIN(current_price::numeric)
              ) / NULLIF(MIN(current_price::numeric), 0) / count(i.stock_code)
            , 1)||'%%' as increase_per_day
          , (select market_value from interest_stocks is2
            	where is2.created_at = max(i.created_at)
            ) as market_value
          , ROUND(avg(current_trading_value::numeric)) as avg_trading_value
          , min(i.created_at)::date as first_date
          , max(i.created_at)::date as last_date
          , s.logo_image_url
          , s.category
          , s.graph_file as s_graph_file
          , to_char(s.close::numeric, 'FM999,999,999') as close
        from interest_stocks i 
        join stocks s on s.stock_code = i.stock_code and s.flag = true
        {favorite_join}
        where 1=1
        and i.market_value::numeric > 70_000_000_000 -- 시총 700억 이상만
        {trading_value_condition}
        --and i.created_at >= NOW() - INTERVAL '1 month'
        --and i.created_at >= CURRENT_DATE - make_interval(days => (CURRENT_DATE - '날짜'::date + 1))
        and i.created_at >= %s::date
        and i.created_at < %s::date + interval '1 day'
        and i.today_price_change_pct is not null
        and i.target = 'interest'
        {target_condition}
        group by i.stock_code, i.stock_name, s.logo_image_url, s.category, s.graph_file, s.close
        having count(i.stock_code) >= 1
        order by count(i.stock_code) desc, max(i.created_at) desc
    ) as b
    left join lateral (
      select i2.current_trading_value::numeric as last_trading_value_num, i2.graph_file
      from interest_stocks i2
      where i2.stock_code = b.stock_code            
      order by i2.created_at desc, i2.id desc
      limit 1
    ) last_i on true
    {fire_condition}
    ;
    """
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur: # namedtuple_row는 컬럼명을 속성명으로 쓴다
        # logger.info("SQL=%s params=%s", sql, params)  # 쿼리 콘솔 출력
        cur.execute(sql, tuple(params))
        # cur.execute(sql, (date,))
        # cur.execute(sql, )
        rows = cur.fetchall()
    return rows


# 사용자와 상관없이 즐겨찾기가 되어 있는 종목 리스트 리턴
@db_transaction
def get_favorite_stocks_info_api(date: str = None, user_id: int = None, conn=None):
    base_sql = """
        select i.stock_code
             , i.stock_name
        from interest_stocks i 
        join favorite_stocks f on f.stock_code = i.stock_code and f.flag = true
        where 1=1
    """
    params = []
    if date is not None:
        base_sql += " and i.created_at >= %s::date"
        params.append(date)

    base_sql += " group by i.stock_code, i.stock_name;"

    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(base_sql, params)
        rows = cur.fetchall()
    return rows



# 저점 데이터 중에서 갱신이 되지 않은 데이터를 반환 (타겟 아웃)
@db_transaction
def get_today_low_stocks(conn=None):
    sql = """
    select id, updated_at, nation, stock_code, stock_name, target 
    from interest_stocks 
    where target like 'low%%'
      and created_at::date = now()::date
      and updated_at <= now() - interval '15 minutes'
    """

    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    return rows

# 실시간 데이터 중에서 갱신이 되지 않은 데이터를 반환 (타겟 아웃)
@db_transaction
def get_today_interest_stocks(conn=None):
    sql = """
    select id, updated_at, nation, stock_code, stock_name, target 
    from interest_stocks 
    where target = 'interest'
      and created_at::date = now()::date
      and updated_at <= now() - interval '15 minutes'
    """

    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    return rows

# 데이터 중에서 타겟에서 아웃된 종목을 target = 'break_away' 처리
#     delete from interest_stocks
#     where id = %s
@db_transaction
def update_stocks_break_away(stock, conn=None):
    origin_target = stock["target"]

    if origin_target.startswith("low"):
        breakaway_target = "breakaway_low"
    elif origin_target == "interest":
        breakaway_target = "breakaway"
    else:
        raise ValueError(f"지원하지 않는 target 값입니다: {origin_target}")

    delete_sql = """
    DELETE FROM interest_stocks
    WHERE stock_code = %s
      AND created_at::date = now()::date
      AND target = %s
      AND id <> %s;
    """

    update_sql = """
    UPDATE interest_stocks
    SET
        target = %s,
        updated_at = now()
    WHERE id = %s
    RETURNING stock_code;
    """

    with conn.cursor() as cur:
        cur.execute(
            delete_sql,
            (
                stock["stock_code"],
                breakaway_target,
                stock["id"],
            )
        )

        cur.execute(
            update_sql,
            (
                breakaway_target,
                stock["id"],
            )
        )

        row = cur.fetchone()

    return row[0] if row else None


@db_transaction
def update_stocks_product_code(stock_code, product_code, conn=None):
    sql = """
    update stocks
    set 
        product_code = %s,
        updated_at = now()
    where stock_code = %s
      and flag = True
    returning stock_code;
    """

    with conn.cursor() as cur:
        cur.execute(sql, (product_code, stock_code,))
        row = cur.fetchone()

    return row[0] if row else None