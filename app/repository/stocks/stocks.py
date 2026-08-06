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


# 종목명 부분 일치로 종목코드 조회 (모의투자 매수 입력창에서 한글 종목명 -> 코드 변환용)
@db_transaction
def find_stocks_by_name_prefix(name_prefix: str, conn=None) -> List[dict]:
    sql = """
    SELECT stock_code, stock_name
    FROM stocks
    WHERE stock_name LIKE %s
    ORDER BY id
    LIMIT 20;
    """
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(sql, (f"%{name_prefix}%",))
        return cur.fetchall()


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


# ── reserved_stocks (자동매수 대상으로 직접 체크한 종목) ─────────────────────
# favorite_stocks와 동일 구조(id/created_at/updated_at/user_id/stock_code/flag,
# (stock_code, user_id) 유니크). 즐겨찾기는 '보기 편하려고' 담는 것이고,
# reserved는 'fire 자동매수 대상으로 쓰겠다'는 의미라 테이블을 분리해서 쓴다.

@db_transaction
def get_reserved_stocks(user_id, conn=None):
    sql = """
    select stock_code from reserved_stocks
    where user_id = %s
    and flag = True;
    """
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(sql, (user_id,))
        rows = cur.fetchall()
    return rows


@db_transaction
def get_reserved_stock_codes(conn=None) -> set:
    """flag=true인 reserved 종목코드 전체(사용자 무관) — 배치(자동매수) 잡에서 사용.
    스케줄러에는 로그인 세션이 없어 user_id를 특정할 수 없고, 이 계좌는 단일 사용자 기준이라
    get_favorite_stocks_info_api()와 동일하게 user 필터 없이 조회한다."""
    with conn.cursor() as cur:
        cur.execute("select distinct stock_code from reserved_stocks where flag = True;")
        return {str(r[0]).zfill(6) for r in cur.fetchall() if r[0]}


@db_transaction
def upsert_reserved_stocks(stock: "StockDTO", conn=None) -> int:
    with conn.cursor() as cur:
        sql = """
        INSERT INTO reserved_stocks (
            created_at, updated_at, user_id, stock_code, flag
        )
        VALUES (
            now(), now(), %s, %s, True
        )
        ON CONFLICT (stock_code, user_id)
        DO UPDATE SET
            updated_at               = now(),
            flag                     = NOT reserved_stocks.flag
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
            graph_file, market_value, target, find_rule
        )
        VALUES (
            now(), now(), %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s
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
            market_value             = COALESCE(EXCLUDED.market_value,             interest_stocks.market_value),
            --target                   = COALESCE(EXCLUDED.target,                   interest_stocks.target)
            find_rule                = COALESCE(EXCLUDED.find_rule,                interest_stocks.find_rule)
        RETURNING id;
        """
        cur.execute(
            sql,
            (
                stock.nation, stock.stock_code, stock.stock_name, stock.pred_price_change_3d_pct,
                stock.yesterday_close, stock.current_price, stock.today_price_change_pct,
                stock.avg5d_trading_value, stock.current_trading_value,
                stock.trading_value_change_pct, stock.graph_file, stock.market_value,
                stock.target, stock.find_rule
            )
        )
        row = cur.fetchone()
        return row[0] if row else None


# interest 종목 가격 데이터 갱신
@db_transaction
def update_interest_stock_close_correctly_list(stocks, conn=None):
    sql = """
        UPDATE interest_stocks s
        SET
            yesterday_close        = COALESCE(%s, s.yesterday_close),
            current_price          = COALESCE(%s, s.current_price),
            today_price_change_pct = COALESCE(%s, s.today_price_change_pct),
            target                 = COALESCE(%s, s.target)
        WHERE s.stock_code       = %s
          AND s.target           = 'interest'
          AND s.created_at::date = %s
          AND NOT EXISTS (
              SELECT 1
              FROM interest_stocks x
              WHERE x.stock_code = s.stock_code
                AND x.target = %s
                AND x.created_at::date = s.created_at::date
                AND x.id <> s.id
          )
        RETURNING s.id, s.stock_code, s.target;
    """

    updated_rows = []
    skipped_rows = []

    with conn.cursor() as cur:
        for stock in stocks:
            cur.execute(
                sql,
                (
                    stock.yesterday_close,
                    stock.current_price,
                    stock.today_price_change_pct,
                    stock.target,

                    stock.stock_code,
                    stock.created_at,

                    stock.target,
                )
            )

            row = cur.fetchone()

            if row:
                updated_rows.append({
                    "id": row[0],
                    "stock_code": row[1],
                    "target": row[2],
                })
            else:
                skipped_rows.append({
                    "stock_code": stock.stock_code,
                    "target": stock.target,
                    "created_at": stock.created_at,
                    "reason": "duplicate target exists or matching interest row not found",
                })

    return {
        "updated_count": len(updated_rows),
        "skipped_count": len(skipped_rows),
        "updated_rows": updated_rows,
        "skipped_rows": skipped_rows,
    }

# 상승주 그래프만 갱신
@db_transaction
def update_interest_stock_graph(stock: "StockDTO", conn=None) -> None:
    sql = """
        UPDATE stocks 
        SET 
            graph_file  = COALESCE(%s, graph_file)
            --updated_at = now() 
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
            graph_file  = COALESCE(%s, graph_file)
            --updated_at = now() 
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
def get_interest_stocks(date: str, endDate: str, mode: str = "normal", rule: str = None, conn=None):
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
        , i.find_rule
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
        if rule in ("low_v1", "low_v2"):
            base_sql += "  AND i.target = %s\n"
            params.append(rule)
        else:
            base_sql += "  AND i.target LIKE 'low%%'\n"
        base_sql += """
          AND i.today_price_change_pct::numeric > 3.3
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
def get_interest_stocks_info(date: str, endDate: str, user_id: int = None, source: str = 'favorite', conn=None):
    # user_id 있을 때만: favorite/reserved join + current_trading_value 컬럼 추가
    favorite_join = ""
    target_condition = ""
    fire_condition = ""
    trading_value_condition = ""

    if user_id is not None:
        # SQL 인젝션 방지: 외부 문자열을 그대로 넣지 않고 화이트리스트로만 테이블명 결정
        member_table = {'favorite': 'favorite_stocks', 'reserved': 'reserved_stocks'}.get(source)
        if member_table is None:
            raise ValueError(f'지원하지 않는 source: {source}')
        favorite_join = f"""
            join {member_table} f on f.stock_code = s.stock_code and f.flag = true and f.user_id = %s
        """
        params = [user_id, date, endDate]
    else:
        trading_value_condition = """
            AND b.avg_trading_value::numeric > 4_000_000_000 -- 최소 거래대금 수정 40억
            AND b.last_trading_value > 4_000_000_000
        """
        target_condition = """
            AND i.target = 'interest'
        """
        fire_condition = """
            where 1=1
            -- 아직 너무 많이 오르지는 않았지만 상승 흐름은 확인된 구간
			AND b.total_rate_of_increase BETWEEN 8 AND 12
			-- AND b.last_today_price_change_pct BETWEEN 3 AND 11
            -- 너무 느린 종목과 급격하게 오른 종목 제외
			-- AND b.increase_per_day BETWEEN 3 AND 6
            AND min_close::numeric < current_close::numeric
            -- 현재가가 조회 기간 최고 관측가격에서 3퍼센트 이상 밀리지 않은 종목
            AND b.current_close >= b.high_close * 0.97
            AND b.market_value > 70_000_000_000
              /*
               * 한국시간 기준:
               *
               * 1. endDate가 과거 날짜면 last_date 조건 미적용
               * 2. endDate가 오늘이어도 09:00 이전이면 조건 미적용
               * 3. endDate가 오늘이고 09:00 이후라면
               *    오늘 interest 신호가 발생한 종목만 통과
               */
              AND (
                     %s::date
                         <> (
                             CURRENT_TIMESTAMP
                             AT TIME ZONE 'Asia/Seoul'
                         )::date
                  OR (
                         CURRENT_TIMESTAMP
                         AT TIME ZONE 'Asia/Seoul'
                     )::time < TIME '09:00:00'
                  OR b.last_date = %s::date
              )
        """
        params = [date, endDate, endDate, endDate]

    sql = f"""
    select 
        row_number() over (
            order by total_rate_of_increase::numeric desc
        ) as rn
        , b.id
        , b.stock_name
        , b.stock_code
        , b.category
        , b.signal_days AS count
        , to_char(b.min_close, 'FM999,999,999') as min_close
        , to_char(b.high_close, 'FM999,999,999') as high_close
        , to_char(b.current_close, 'FM999,999,999') as current_close
        , b.total_rate_of_increase ||'%%' as total_rate_of_increase
        , b.increase_per_day || '%%' as increase_per_day
        , b.market_value
        , b.avg_trading_value
        , b.last_trading_value
        , b.first_date
        , b.last_date
        , b.logo_image_url
        , coalesce(b.s_graph_file, b.last_graph_file) as graph_file
    from (
        select 
          max(i.id) as id
          , i.stock_code
          , i.stock_name
          , COUNT(DISTINCT i.created_at::date) AS signal_days
          , s.close::numeric as current_close
          , min(i.current_price::numeric) as min_close
          , MAX(i.current_price::numeric) as high_close
          , ROUND(
              100.0 * (
                  CASE
                      WHEN MAX(i.created_at)::date <> CURRENT_DATE
                      THEN (
                          ARRAY_AGG(
                              i.current_price::numeric
                              ORDER BY i.created_at DESC, i.id DESC
                          )
                      )[1]
                      ELSE s.close::numeric
                  END
                  - MIN(i.current_price::numeric)
              )
              / NULLIF(MIN(i.current_price::numeric), 0)
          , 1) AS total_rate_of_increase
          , ROUND(
              100.0 * (
                  CASE
                      WHEN MAX(i.created_at)::date <> CURRENT_DATE
                      THEN (
                          ARRAY_AGG(
                              i.current_price::numeric
                              ORDER BY i.created_at DESC, i.id DESC
                          )
                      )[1]
                      ELSE s.close::numeric
                  END
                  - MIN(i.current_price::numeric)
              ) / NULLIF(MIN(i.current_price::numeric), 0) / count(DISTINCT i.created_at::date)
            , 1) as increase_per_day
          , (
                ARRAY_AGG(
                    i.market_value::numeric
                    ORDER BY i.created_at DESC, i.id DESC
                )
        	)[1] AS market_value
          , ROUND(avg(i.current_trading_value::numeric)) as avg_trading_value
          , (
              ARRAY_AGG(
                  i.current_trading_value::numeric
                  ORDER BY i.created_at DESC, i.id DESC
              )
          )[1] AS last_trading_value
          , (
              ARRAY_AGG(
                  i.graph_file
                  ORDER BY i.created_at DESC, i.id DESC
              )
          )[1] AS last_graph_file
          , (
              ARRAY_AGG(
                  i.today_price_change_pct::numeric
                  ORDER BY i.created_at DESC, i.id DESC
              )
          )[1] AS last_today_price_change_pct
          , min(i.created_at)::date as first_date
          , max(i.created_at)::date as last_date
          , s.logo_image_url
          , s.category
          , s.graph_file as s_graph_file
        from interest_stocks i 
        join stocks s on s.stock_code = i.stock_code and s.flag = true
        {favorite_join}
        where 1=1
        and i.created_at >= %s::date
        and i.created_at < %s::date + interval '1 day'
        {target_condition}
        group by i.stock_code, i.stock_name, s.logo_image_url, s.category, s.graph_file, s.close
        having COUNT(DISTINCT i.created_at::date) >= 2
    ) as b
    {fire_condition}
    {trading_value_condition}
    ORDER BY total_rate_of_increase::numeric DESC
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