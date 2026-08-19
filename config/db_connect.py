from typing import Dict, Any

import atexit
import psycopg
import psycopg_pool
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

# 풀 객체 생성
db_pool = psycopg_pool.ConnectionPool(
    conninfo=(
        f"dbname={db_settings['db']['DB_NAME']} "
        f"user={db_settings['db']['DB_USERNAME']} "
        f"password={db_settings['db']['DB_PASSWORD']} "
        f"host={db_settings['db']['DB_HOST']} "
        f"port={db_settings['db']['DB_PORT']}"
    ),
    min_size=1,  # 최소 커넥션
    max_size=10, # 최대 커넥션
    timeout=10   # 커넥션이 모두 사용 중이면 최대 10초 대기 후 에러
)

# 명시적으로 close()하지 않으면 인터프리터 종료 시 __del__이 워커 스레드(pool-1-worker-*,
# pool-1-scheduler)를 5초 타임아웃으로 정리하는데, 그 시점엔 인터프리터가 이미 종료 중이라
# 스레드 join이 실패하기 쉽다 — "couldn't stop thread ... within 5.0 seconds" 경고 원인
# (psycopg_pool/pool.py __del__ 참고). atexit에서 먼저 close()해두면 __del__은 이미 닫힌
# 걸 보고 그냥 반환한다.
atexit.register(db_pool.close)

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