import configparser
from werkzeug.security import generate_password_hash
from typing import Dict, List, Any
from psycopg.rows import dict_row
from config.db_connect import db_transaction
import logging



def read_ini_sections(path: str) -> Dict[str, Dict[str, str]]:
    """
    INI 파일을 섹션별 dict로 변환.

    import configparser

    config = configparser.ConfigParser()
    config.read('config/config.ini', encoding='utf-8')

    print(config.sections())                # ['settings', 'directories']; config.sections(): INI 파일 안의 섹션 이름 목록 (문자열 리스트) 반환
    print(config['settings']['username'])   # 'fkaus14'
    """
    config = configparser.ConfigParser()
    with open(path, "r", encoding="utf-8") as f:
        config.read_file(f)

    # 딕셔너리 내포 (comprehension)
    return {s: dict(config[s]) for s in config.sections()} # config.sections(): INI 파일 안의 섹션 이름 목록 (문자열 리스트) 반환


@db_transaction
def fetch_configs_rows(enabled_only: bool = True, conn=None) -> List[Dict[str, Any]]:
    '''
    파이썬의 조건부 표현식(ternary operator)
    # 형태
    <참일 때 값> if <조건> else <거짓일 때 값>
    '''
    where = "WHERE is_active IS TRUE" if enabled_only else ""
    sql = f"""
        SELECT section, key, value
        FROM configs
        {where}
        ORDER BY id
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql)
        return list(cur.fetchall())


def rows_to_by_section(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    """
    DB rows를 {section: {key: value}} 구조로 변환.
    """
    by_section: Dict[str, Dict[str, str]] = {}
    for r in rows:
        sec = (r.get("section") or "").strip()
        key = (r.get("key") or "").strip()
        val = r.get("value")
        if not sec or not key:
            continue
        by_section.setdefault(sec, {})[key] = val
    return by_section


def map_runtime_config(by_section: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    """
    기존 코드 인터페이스에 맞춰 필요한 키만 뽑아 최종 dict를 만든다.
    """
    settings = by_section.get("settings", {})
    directories = by_section.get("directories", {})
    urls = by_section.get("urls", {})
    paths = by_section.get("paths", {})
    lotto = by_section.get("lotto", {})
    auth = by_section.get("auth", {})
    meta = by_section.get("meta", {})
    db = by_section.get("db", {})

    return {
        # 기존 반환 구조와 호환되게 매핑
        'SECRET_KEY': settings.get('secret_key'),
        'MUD_USERNAME': settings.get('mudfish_username'),
        'MUD_PASSWORD': settings.get('mudfish_password'),
        'USERNAME': settings.get('username'),
        'PASSWORD': generate_password_hash(settings.get('password')), # generate_password_hash 는 솔트가 있어서 매번 다른 값이 나온다. DB 검증에는 사용하지 않는다.
        'GUEST_USERNAME': settings.get('guest_username'),
        'GUEST_PASSWORD': generate_password_hash(settings.get('guest_password')),
        'SUPER_USERNAME': settings.get('super_username'),
        'SUPER_PASSWORD': generate_password_hash(settings.get('super_password')),
        'SCRAP_USERNAME': settings.get('scrap_username'),
        'SCRAP_PASSWORD': settings.get('scrap_password'),

        'VIDEO_DIRECTORY0': directories.get('ffmpeg_directory'),
        'VIDEO_DIRECTORY1': directories.get('video_directory1'),
        'VIDEO_DIRECTORY2': directories.get('video_directory2'),
        'VIDEO_DIRECTORY3': directories.get('video_directory3'),
        'VIDEO_DIRECTORY4': directories.get('video_directory4'),
        'VIDEO_DIRECTORY5': directories.get('video_directory5'),
        'TT_DIRECTORY': directories.get('video_directory6'),
        'VIDEO_DIRECTORY10': directories.get('video_directory10'),
        'IMAGE_DIR': directories.get('images_directory'),
        'IMAGE_DIR2': directories.get('images_directory2'),
        'MOVE_DIR': directories.get('move_images_directory'),
        'REF_IMAGE_DIR': directories.get('refined_images_directory'),
        'TRIP_IMAGE_DIR': directories.get('trip_images_directory'),
        'TEMP_IMAGE_DIR': directories.get('temp_images_directory'),
        'DEL_TEMP_IMAGE_DIR': directories.get('del_temp_images_directory'),
        'KOSPI_DIR': directories.get('kospi_stocks_directory'),
        'SP500_DIR': directories.get('sp500_stocks_directory'),
        'INTEREST_DIR': directories.get('interest_stocks_directory'),
        'NODE_SERVER_PATH': directories.get('node_server_path'),
        'HTM_DIRECTORY': directories.get('htm_directory'),

        'CRAWL_URL': urls.get('crawl_url'),
        'MUD_VPN': urls.get('mud_vpn'),
        'COOKIE': urls.get('cookie'),
        'CRAWL_HOST': urls.get('crawl_host'),

        'FFMPEG_SCRIPT_PATH': paths.get('ffmpeg_script_path'),
        'WORK_DIRECTORY': paths.get('work_directory'),

        'LOTTO_USER_ID': lotto.get('username'),
        'LOTTO_PASSWORD': lotto.get('password'),

        'SECOND_PASSWORD_SESSION_KEY': auth.get('second_password_session_key'),
        'YOUR_SECRET_PASSWORD': auth.get('your_secret_password'),

        'FACEBOOK_APP_ID': meta.get('facebook_app_id'),
        'THREADS_APP_ID': meta.get('threads_app_id'),
        'THREADS_APP_SECRET': meta.get('threads_app_secret'),

        'DB_NAME': db.get('db_name'),
        'DB_ID': db.get('db_id'),
        'DB_PASSWORD': db.get('db_password'),
        'DB_HOST': db.get('db_host'),
        'DB_PORT': db.get('db_port'),
    }


# 로더 (DB 우선, 비어있으면 INI 폴백 추가)
def merge_missing_sections(primary: Dict[str, Dict[str, str]], fallback: Dict[str, Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    """
    primary에 없는 fallback 섹션만 추가
    """
    for sec, kv in fallback.items():
        tgt = primary.setdefault(sec, {})
        for k, v in kv.items():
            tgt.setdefault(k, v)   # 이미 있으면 건드리지 않음
    return primary

def load_config(fallback_ini: str = "config/config.ini") -> Dict[str, Any]:
    """
    - DB에서 읽어 섹션 딕셔너리 구성 (실패 시 빈 dict)
    - INI를 읽어 부족한 키만 보충 (DB 값은 덮어쓰지 않음)
    - [db] 섹션만 환경변수로 최종 오버라이드
    - 최종 맵을 런타임 설정으로 매핑
    """
    by_section: Dict[str, Dict[str, str]] = {}

    # 환경 변수 읽어와 DB 커넥션 생성

    # 1) DB 우선
    try:
        rows = fetch_configs_rows()                # @db_transaction 내부에서 conn 주입
        by_section = rows_to_by_section(rows)      # Dict[str, Dict[str, str]]
    except Exception:
        logging.exception("load_config: DB fetch/transform failed")  # 스택 포함 로그
        by_section = {}

    # 2) INI 폴백으로 '없는 키만' 보충
    try:
        ini_map = read_ini_sections(fallback_ini)  # Dict[str, Dict[str, str]]
    except Exception:
        ini_map = {}

    merged = merge_missing_sections(by_section, ini_map)

    # 3) 최종 매핑 반환 (기존 map_runtime_config에 [db]도 필요하면 반영)
    return map_runtime_config(merged)


settings = load_config()







'''
dick: key-value 가변 컨테이너

# 생성
d = {"name": "Inwoo", "age": 33}
d2 = dict([("a", 1), ("b", 2)])
d3 = dict(zip(["x", "y"], [10, 20]))

# 조회
d["name"]            # 키 없으면 KeyError
d.get("name")        # 키 없으면 None (기본값 지정 가능)
d.get("job", "N/A")  # 'N/A'

# 추가/수정
d["city"] = "Seoul"
d.update({"age": 34, "job": "dev"})

# 삭제
d.pop("age")         # 키 없으면 KeyError (기본값 인수로 방지 가능)
d.popitem()          # 마지막 쌍 하나 제거 (LIFO)
del d["city"]

# 존재 확인
"name" in d          # True
'''


'''
유용한 메서드/패턴

# 안전한 기본값 넣기
d.setdefault("count", 0)           # 없으면 0으로 넣고 반환

# 뷰 객체(실시간 반영)
d.keys(); d.values(); d.items()

# 얕은/깊은 복사
shallow = d.copy()
import copy; deep = copy.deepcopy(d)

# 딕셔너리 병합 (3.9+)
merged = d | {"lang": "ko"}        # 새 dict
d |= {"lang": "ko"}                # 제자리 업데이트

# 딕셔너리 내포
squares = {n: n*n for n in range(5)}

# 중첩 접근 (KeyError 방지)
user = {"profile": {"name": "Inwoo"}}
name = user.get("profile", {}).get("name")  # "Inwoo"
'''



'''
변형 타입

from collections import defaultdict, Counter

# 기본값 자동 생성
dd = defaultdict(int)
dd["a"] += 1       # {'a': 1}

# 빈도 카운트
cnt = Counter("banana")  # Counter({'a':3, 'n':2, 'b':1})
'''
