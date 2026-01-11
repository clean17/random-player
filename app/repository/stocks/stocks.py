from typing import List, Sequence, Tuple
from config.db_connect import db_transaction
import psycopg


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
    SELECT stock_code, stock_name, sector_code, stock_market 
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
            graph_file               = COALESCE(EXCLUDED.graph_file,               interest_stocks.graph_file),
            market_value             = COALESCE(EXCLUDED.market_value,             interest_stocks.market_value),
            target                   = COALESCE(EXCLUDED.target,                   interest_stocks.target)
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

# 오늘의 실시간 등락
@db_transaction
def get_interest_stocks(date: str, conn=None):
    sql = """
    SELECT i.id
         , i.created_at
         , i.stock_code
         , i.stock_name
         , i.pred_price_change_3d_pct
         , i.yesterday_close
         , i.current_price
         , i.today_price_change_pct
         , i.avg5d_trading_value
         , i.current_trading_value
         , i.trading_value_change_pct
         , i.graph_file
         , i.updated_at
         , i.market_value
         , case when market_value::numeric >= 1_000_000_000_000
      		 then ROUND(market_value::numeric/1_000_000_000_000, 1)||'조'
             else ROUND(market_value::numeric/100_000_000)||'억'
             end as market_value_fmt
         , s.category
         , s.close
         , s.logo_image_url
    FROM interest_stocks i, stocks s
    WHERE i.created_at::date = %s
    and i.stock_code = s.stock_code
    and s.flag = True
    AND i.today_price_change_pct::float >= 4
    AND i.current_trading_value::numeric > 5_000_000_000
    AND i.target is null
    ORDER BY i.today_price_change_pct::numeric DESC, i.current_trading_value::numeric DESC;   
    """
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur: # namedtuple_row는 컬럼명을 속성명으로 쓴다
        cur.execute(sql, (date,))
        rows = cur.fetchall()
    return rows


# 최근 상승주 검색
@db_transaction
def get_interest_stocks_info(date: str, user_id: int = None, conn=None):
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
        params = [user_id, date]
    else:
        trading_value_condition = """
            and i.current_trading_value::numeric > 4_000_000_000 -- 최소 거래대금 수정 40억
        """
        target_condition = """
            and i.target is null
        """
        fire_condition = """
            where REGEXP_REPLACE(avg_change_pct, '%%', '', 'g')::numeric > 5
            and REGEXP_REPLACE(total_rate_of_increase, '%%', '', 'g')::numeric > 7
            and REGEXP_REPLACE(increase_per_day, '%%', '', 'g')::numeric < 20
            and REGEXP_REPLACE(increase_per_day, '%%', '', 'g')::numeric > 3.2
        """
        params = [date]

    sql = f"""
    select row_number() over (
        order by count desc
        , REGEXP_REPLACE(avg_change_pct, '%%', '', 'g')::numeric desc
        , REGEXP_REPLACE(total_rate_of_increase, '%%', '', 'g')::numeric desc
        ) as rn
        , b.* 
        , ROUND(last_i.last_trading_value_num / 100_000_000) || '억' as current_trading_value
        , coalesce(b.s_graph_file, last_i.graph_file) as graph_file
    from (
        select 
          max(i.id) as id
          , i.stock_code
          , I.stock_name
          , count(i.stock_code)
          , to_char(min(current_price::numeric), 'FM999,999,999') as min
          , to_char(coalesce(s.close::numeric, max(i.current_price::numeric)), 'FM999,999,999') as last
          , ROUND(
              AVG(
                COALESCE(
                  NULLIF(REGEXP_REPLACE(today_price_change_pct, '%%', '', 'g'), '')::numeric, 0)
               )
            , 1)||'%%' AS avg_change_pct  
          , ROUND(100.0 * (coalesce(coalesce(s.close::numeric, max(i.current_price::numeric)), 0) - MIN(current_price::numeric))
               / NULLIF(MIN(current_price::numeric), 0),1)||'%%' AS total_rate_of_increase
          , ROUND(100.0 * (coalesce(coalesce(s.close::numeric, max(i.current_price::numeric)), 0) - MIN(current_price::numeric))
               / NULLIF(MIN(current_price::numeric), 0)  / count(i.stock_code), 1)||'%%' as increase_per_day
          , case when max(market_value::numeric) >= 1_000_000_000_000
          		 then ROUND(max(market_value::numeric)/1_000_000_000_000, 1)||'조'
                 else ROUND(max(market_value::numeric)/100_000_000)||'억'
                 end as market_value
          , ROUND(avg(current_trading_value::numeric)/100000000)||'억' as avg_trading_value
          , min(i.created_at)::date as first_date
          , max(i.created_at)::date as last_date
          , s.logo_image_url
          , s.category
          , s.graph_file as s_graph_file
        from interest_stocks i 
        join stocks s on s.stock_code = i.stock_code and s.flag = true
        {favorite_join}
        where 1=1
        and i.market_value::numeric > 50_000_000_000
        {trading_value_condition}
        --and i.created_at >= NOW() - INTERVAL '1 month'
        --and i.created_at >= CURRENT_DATE - make_interval(days => (CURRENT_DATE - '날짜'::date + 1))
        and i.created_at >= %s::date
        and today_price_change_pct is not null
        {target_condition}
        group by i.stock_code, i.stock_name, s.close, s.logo_image_url, s.category, s.graph_file
        having count(i.stock_code) >= 1
--            and count(stock_code) <= 6
        and max(i.created_at) >= (CURRENT_DATE - INTERVAL '7 days') -- x일 전부터 등록된 것
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
        cur.execute(sql, tuple(params))
        # cur.execute(sql, (date,))
        # cur.execute(sql, )
        rows = cur.fetchall()
    return rows


# 사용자와 상관없이 즐겨찾기가 되어 있는 종목 리스트 리턴
@db_transaction
def get_favorite_stocks_info_api(date: str, user_id: int = None, conn=None):
    sql = f"""
    select i.stock_code
         , i.stock_name
    from interest_stocks i 
    join favorite_stocks f on f.stock_code = i.stock_code and f.flag = true
    where 1=1
    and i.created_at >= %s::date
    group by i.stock_code, i.stock_name
    ;
    """
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur: # namedtuple_row는 컬럼명을 속성명으로 쓴다
        cur.execute(sql, (date,))
        rows = cur.fetchall()
    return rows


# 저점 매수 검색
@db_transaction
def get_interest_low_stocks(date: str, conn=None):
    sql = """
    SELECT i.id
         , i.graph_file
         , i.stock_name
         , i.stock_code        
         , i.created_at
         , i.yesterday_close
         , i.current_price
         , i.today_price_change_pct
         , i.avg5d_trading_value
         , i.current_trading_value
         , i.trading_value_change_pct
         , case when market_value::numeric >= 1_000_000_000_000
      		 then ROUND(market_value::numeric/1_000_000_000_000, 1)||'조'
             else ROUND(market_value::numeric/100_000_000)||'억'
             end as market_value  
         , s.close
         , s.logo_image_url
         , s.category
    FROM interest_stocks i, stocks s
    WHERE i.created_at::date = %s
    and i.stock_code = s.stock_code
    and s.flag = True
    AND i.today_price_change_pct::numeric > 3.8
    AND i.target = 'low'
    ORDER BY i.today_price_change_pct::numeric DESC;
    """
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur: # namedtuple_row는 컬럼명을 속성명으로 쓴다
        cur.execute(sql, (date,))
        rows = cur.fetchall()
    return rows
