import psycopg
import psycopg_pool
from config.config import settings

conn = psycopg.connect(
    dbname=settings['DB_NAME'],
    user=settings['DB_ID'],
    password=settings['DB_PASSWORD'],
    host=settings['DB_HOST'],
    port=settings['DB_PORT']
)

# 풀 객체 생성
db_pool = psycopg_pool.ConnectionPool(
    conninfo=(
        f"dbname={settings['DB_NAME']} "
        f"user={settings['DB_ID']} "
        f"password={settings['DB_PASSWORD']} "
        f"host={settings['DB_HOST']} "
        f"port={settings['DB_PORT']}"
    ),
    min_size=1,  # 최소 커넥션
    max_size=10, # 최대 커넥션
    timeout=10   # 커넥션이 모두 사용 중이면 최대 10초 대기 후 에러
)

# 데코레이터(Decorator), 함수를 인자로 받아서 트랜잭션 처리를 자동화
def db_transaction(func):
    def wrapper(*args, **kwargs): # 모든 인자(*args, **kwargs)를 그대로 받는다
        with db_pool.connection() as conn: # 풀에서 커넥션을 with로 빌려옴 > 블록이 끝나면 자동 반환(정리)
            try:
                result = func(*args, conn=conn, **kwargs)
                conn.commit()
                return result
            except Exception as e:
                conn.rollback()
                raise # 예외를 밖으로 던진다
    return wrapper # @db_transaction를 함수 위에 붙이면 원래 함수 대신 wrapper가 호출된다