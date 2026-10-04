import os
import time
import json
import logging
import threading
import requests
from datetime import datetime, date, timedelta, time as _dtime
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv, find_dotenv

dotenv_path = find_dotenv(usecwd=True) or ".env"
load_dotenv(dotenv_path=dotenv_path)

# KIWOOM_ENV=mock(기본, 모의투자) / real(실전투자) — .env에서 전환
# 실전 전환 전 반드시 모의투자로 응답 필드명·수량 계산을 검증할 것
KIWOOM_ENV = os.environ.get('KIWOOM_ENV', 'mock')

_ENV_CONFIG = {
    'mock': {
        'base_url': 'https://mockapi.kiwoom.com',
        'app_key_env': 'KIWOOM_MOCK_APP_KEY',
        'secret_key_env': 'KIWOOM_MOCK_SECRET_KEY',
        'token_env': 'KIWOOM_MOCK_ACCESS_TOKEN',
        'acnt_no_env': 'KIWOOM_MOCK_ACNT_NO',
        'acnt_pwd_env': 'KIWOOM_MOCK_ACNT_PWD',
    },
    'real': {
        'base_url': 'https://api.kiwoom.com',
        'app_key_env': 'KIWOOM_APP_KEY',
        'secret_key_env': 'KIWOOM_SECRET_KEY',
        'token_env': 'KIWOOM_ACCESS_TOKEN',
        'acnt_no_env': 'KIWOOM_ACNT_NO',
        'acnt_pwd_env': 'KIWOOM_ACNT_PWD',
    },
}

_cfg = _ENV_CONFIG[KIWOOM_ENV]
BASE_URL = _cfg['base_url']     # 프로세스 기본 환경의 호스트. env 인수를 쓰는 경로는 _cfg_for()를 볼 것
VALID_ENVS = tuple(_ENV_CONFIG)


def _cfg_for(env: Optional[str] = None) -> dict:
    """환경 설정 딕셔너리. env가 None이면 프로세스 기본값(KIWOOM_ENV).

    2026-08-20 추가 — 대시보드에서 모의/실전 계좌를 **동시에 조회**하기 위해 환경을 호출
    인수로 받을 수 있게 했다. 기존 호출부는 전부 인수 없이 부르므로 동작이 바뀌지 않는다
    (스케줄러·자동매매는 여전히 .env의 KIWOOM_ENV 하나만 쓴다).
    """
    if env is None:
        return _cfg
    if env not in _ENV_CONFIG:
        raise ValueError('알 수 없는 KIWOOM 환경: {!r} (가능: {})'
                         .format(env, ', '.join(_ENV_CONFIG)))
    return _ENV_CONFIG[env]


def get_account_credentials(env: Optional[str] = None) -> tuple:
    """KIWOOM 환경(mock/real)에 맞는 계좌번호/비밀번호를 반환. 모의·실전 계좌번호는 서로 다르므로
    호출부에서 acnt_no를 직접 .env 키로 읽지 말고 반드시 이 함수를 통해서만 가져올 것."""
    c = _cfg_for(env)
    return os.environ.get(c['acnt_no_env']), os.environ.get(c['acnt_pwd_env'])


# KRX 공식 휴장일(주말 제외, 평일인데 장이 안 열리는 날). 대체공휴일·임시공휴일·선거일 포함.
# 2026-09-24 사고 계기로 추가 — is_market_open() 계열 함수가 전부 "월~금이면 영업일"로만
# 보고 있어서, 추석 등 평일 공휴일에 청산 주문을 거부(RC4010/RC4058)당할 때까지 30초/60초마다
# 계속 시도했다. (보유일수 계산 자체는 TRADING_RULES.md 1-2절 백테스트 근거로 일부러 그대로 둠.)
#
# 최초엔 이 목록을 하드코딩했으나(교차검증한 15일), 검증 도중 2026-06-03 지방선거 휴장일이
# 그 방식으로는 빠져있었던 걸 발견했다(선거일은 연초 시판 캘린더에 없고 그때그때 공고된다) —
# 그래서 한국천문연구원 "특일 정보" API(공공데이터포털, .env KASI_HOLIDAY_API_KEY)로 자동
# 갱신하도록 바꿨다. KRX 정기휴장일 규정(공휴일+근로자의날+토요일+일요일+12/31, 그 외 임시
# 공휴일·선거일 포함)이 이 API의 isHoliday=Y 판정과 정확히 일치함을 실측 확인(2026-09-24,
# 아래 소스 대조: 현충일 6/6은 그 해 토요일이라 무관, 제헌절 7/17은 2026년에 한시적으로 법정
# 공휴일 재지정돼 실제로 KRX도 휴장 — API가 이걸 정확히 잡아냈다).
KRX_HOLIDAY_API_URL = ('https://apis.data.go.kr/B090041/openapi/service/'
                        'SpcdeInfoService/getHoliDeInfo')
_KRX_HOLIDAY_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        'krx_holidays_cache.json')

# 최후 폴백(API 키 미설정·최초 실행 시 캐시 파일도 없을 때만 씀) — 2026-09-24 교차검증.
# ⚠️ 지방선거처럼 그때그때 공고되는 휴장일은 여기 못 담는다 — 이 목록은 어디까지나
# API/캐시가 둘 다 실패했을 때의 안전망이지 정답이 아니다.
KRX_HOLIDAYS_2026 = {
    date(2026, 1, 1),
    date(2026, 2, 16), date(2026, 2, 17), date(2026, 2, 18),
    date(2026, 3, 2),
    date(2026, 5, 1), date(2026, 5, 5), date(2026, 5, 25),
    date(2026, 6, 3),  # 전국동시지방선거 (2026-09-24 API 조회로 발견 — 최초 하드코딩엔 누락돼 있었다)
    date(2026, 7, 17),  # 제헌절 (2026년 한시적 법정공휴일 재지정, KRX도 휴장)
    date(2026, 8, 17),
    date(2026, 9, 24), date(2026, 9, 25),
    date(2026, 10, 5), date(2026, 10, 9),
    date(2026, 12, 25), date(2026, 12, 31),
}
KRX_HOLIDAYS = set(KRX_HOLIDAYS_2026)  # refresh_krx_holidays()가 in-place로 갱신 (재바인딩 금지 —
                                        # 다른 모듈이 from ... import KRX_HOLIDAYS 로 참조를 들고 있다)


def _year_end_closure(year: int) -> date:
    """12/31 결산휴장일. 주말이면 KRX 규정대로 직전 평일로 당긴다(다른 공휴일과 겹치는
    희귀 케이스까지는 처리하지 않음 — 실무상 거의 발생하지 않는다)."""
    d = date(year, 12, 31)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _fetch_krx_holidays_year(year: int) -> Optional[List[str]]:
    """KASI 특일 정보 API로 한 해 공휴일(YYYYMMDD 문자열 리스트)을 조회. 실패하면 None —
    호출부가 기존 값을 그대로 유지할 수 있게 예외를 던지지 않는다."""
    api_key = os.environ.get('KASI_HOLIDAY_API_KEY')
    if not api_key:
        return None
    try:
        resp = requests.get(KRX_HOLIDAY_API_URL, params={
            'serviceKey': api_key, 'solYear': str(year), 'numOfRows': '100', '_type': 'json',
        }, timeout=10)
        resp.raise_for_status()
        body = resp.json().get('response', {}).get('body', {})
        items = (body.get('items') or {}).get('item') or []
        if isinstance(items, dict):
            items = [items]
        return [str(it['locdate']) for it in items if it.get('isHoliday') == 'Y']
    except Exception as e:
        print(f'[WARN] KASI 휴장일 API 조회 실패({year}년): {e}')
        return None


def _load_krx_holiday_cache_file() -> Dict[str, List[str]]:
    try:
        with open(_KRX_HOLIDAY_CACHE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_krx_holiday_cache_file(cache: Dict[str, List[str]]) -> None:
    tmp = _KRX_HOLIDAY_CACHE_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _KRX_HOLIDAY_CACHE_PATH)  # 원자적 교체 — kiwoom_v8_positions 파일 손상 사고 재발 방지


def _apply_krx_holiday_cache(cache: Dict[str, List[str]]) -> bool:
    """cache({'2026': ['20260101', ...]})를 KRX_HOLIDAYS에 in-place 반영. 파싱 가능한 날짜가
    하나도 없으면 아무것도 바꾸지 않고 False를 반환한다(빈 캘린더로 덮어써 전부 '거래일'로
    오판하는 게 최악의 실패 모드라서)."""
    new_dates = set()
    for year_str, ymd_list in (cache or {}).items():
        try:
            year = int(year_str)
        except ValueError:
            continue
        for ymd in ymd_list:
            try:
                new_dates.add(datetime.strptime(str(ymd), '%Y%m%d').date())
            except ValueError:
                continue
        new_dates.add(_year_end_closure(year))
    if not new_dates:
        return False
    KRX_HOLIDAYS.clear()
    KRX_HOLIDAYS.update(new_dates)
    return True


# 모듈 로드 시: 캐시 파일이 있으면 그걸로 하드코딩 폴백을 즉시 덮어쓴다(로컬 파일 읽기라
# 네트워크 호출 없이 빠르다). 캐시가 없거나 비어있으면 위 KRX_HOLIDAYS_2026 폴백을 그대로 둔다.
_apply_krx_holiday_cache(_load_krx_holiday_cache_file())


def refresh_krx_holidays() -> bool:
    """올해+내년 공휴일을 API로 갱신해 캐시 파일에 저장하고 KRX_HOLIDAYS에 반영한다.
    job/batch_runner.py에 주 1회 스케줄로 등록해서 쓸 것 — 서버가 몇 달씩 재시작 없이 떠
    있어도 새해 캘린더가 자동으로 들어오고, 지방선거처럼 갑자기 공고되는 휴장일도 반영된다.
    ⚠️ API 실패 시 기존 캐시/폴백을 그대로 두고 False를 반환한다 — 절대 빈 값으로 덮지 않는다."""
    this_year = datetime.now().year
    fetched: Dict[str, List[str]] = {}
    for y in (this_year, this_year + 1):
        dates = _fetch_krx_holidays_year(y)
        if dates:
            fetched[str(y)] = dates
    if not fetched:
        return False
    cache = _load_krx_holiday_cache_file()
    cache.update(fetched)
    ok = _apply_krx_holiday_cache(cache)
    if ok:
        _save_krx_holiday_cache_file(cache)
    return ok


def is_krx_holiday(d: Optional[date] = None) -> bool:
    """평일인데 KRX가 쉬는 날인지(주말 여부는 별도로 봐야 함)."""
    d = d or datetime.now().date()
    return d in KRX_HOLIDAYS


def is_krx_business_day(d: Optional[date] = None) -> bool:
    """주말도 KRX_HOLIDAYS도 아닌 실제 개장일인지."""
    d = d or datetime.now().date()
    return d.weekday() < 5 and d not in KRX_HOLIDAYS


def is_krx_aftermarket_open() -> bool:
    """2026-09-14 신설 KRX 애프터마켓(16:00~20:00) — 기존 시간외단일가 폐지하고 대체,
    15:30~16:00 휴장 신설. NXT 애프터마켓(15:30~20:00)과는 별개의 KRX 소속 세션.

    실측 결과(auto_trading/aftermarket_order_test.py):
      · 실전(real) — 시장가는 거부(return_code 20, "[2000](521790:해당 호가유형은 주문
        불가능한 시간입니다.)")되지만 **지정가는 정상 접수·체결**된다(2026-09-14 18:55~19:12,
        v8 트레일링 청산이 지정가로 실제 3건 체결 확인). kiwoom_v8_exit._sell /
        kiwoom_trailing_stop._sell 이 이 시간대엔 지정가로 자동 전환해 대응한다.
      · **모의(mock) — 지정가/시장가 가리지 않고 전부 거부된다**(2026-09-15 19:04 실측,
        `RC4058:모의투자 장종료`). 시세 조회(get_current_price)는 정상 동작하지만 주문
        자체를 아예 안 받는다 — NXT 때(RC9000, "해당업무가 제공되지 않습니다")와 같은
        패턴이다. 그래서 이 함수는 **mock이면 무조건 False**를 반환한다 — mock 프로세스에서
        기다려봐야 되는 주문이 아니므로, 여기서 걸러 fire 매수/레거시 청산이 매 사이클
        RC4058 거부만 반복 기록하지 않게 한다.
    """
    if KIWOOM_ENV != 'real':
        return False
    now = datetime.now()
    if not is_krx_business_day(now.date()):
        return False
    return _dtime(16, 0) <= now.time() < _dtime(20, 0)


def env_path(path: str, env: Optional[str] = None) -> str:
    """상태·이력 파일 경로에 KIWOOM_ENV를 붙여 모의/실전을 분리한다.

        logs/kiwoom_trading/trades.jsonl → trades_real.jsonl   (KIWOOM_ENV=real)
                                         → trades_mock.jsonl   (KIWOOM_ENV=mock)

    ⚠️ 분리하지 않으면 모의계좌 상태가 실전 매매를 조종한다. 2026-08-14 실전 전환 당일
       kiwoom_trailing_state.json에 남아 있던 모의 포지션 상태(후성 093370: peak_rate 11.86%,
       tranche_qty 10)가 그대로 쓰여서, 실계좌 후성이 그 모의 기준선으로 10주 매도됐다.
       실현손익 기준점(asset_baseline)도 모의 자산(749만원)이 실계좌(172만원)에 적용되고 있었다.
    """
    root, ext = os.path.splitext(path)
    if env is not None and env not in _ENV_CONFIG:
        raise ValueError('알 수 없는 KIWOOM 환경: {!r}'.format(env))
    return f'{root}_{env or KIWOOM_ENV}{ext}'


_TRADING_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'logs', 'kiwoom_trading')


def log_event(stream: str, payload: Dict, env: Optional[str] = None) -> None:
    """분석용 이벤트를 JSONL 한 줄로 append 한다 (2026-09-04 추가).

        log_event('v8_signals', {...})  ->  logs/kiwoom_trading/v8_signals_real.jsonl

    왜 trades.jsonl 과 별도인가: trades.jsonl 은 **체결된 거래**만 담는다. 체결되지 않은
    후보·주문·취소는 그동안 텍스트 로그(trading.log, 180일 로테이션)에만 남아서
    "왜 그 종목을 안 샀나 / 랭킹이 몇 위였나 / 며칠 기다렸나"를 사후에 재구성할 수 없었다
    (`TRADING_RULES.md` 8절 1번의 'reserved 이력이 없어 재현 불가'와 같은 문제).

    ⚠️ **이 함수는 절대 예외를 올리지 않는다.** 로깅 실패가 주문을 스킵시키는 일이 있어서는
       안 된다(과거 매수 조용히 스킵 사고 이력 참고). 호출부에서 try 로 감쌀 필요가 없다.
    """
    try:
        path = env_path(os.path.join(_TRADING_LOG_DIR, stream + '.jsonl'), env)
        rec = {'ts': datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}
        rec.update(payload or {})
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + '\n')
    except Exception:
        pass


# ── 자동 재주문 스위치 (2026-09-14) ──────────────────────────────────────────
# 대시보드 '주문 목록'의 [전체 주문 취소] 버튼으로 미체결을 싹 지워도, 자동매매는 다음
# 주기(v8 60초 / fire 애프터마켓 1분)에 같은 후보에 다시 주문을 걸어버린다
# (manual_cancel_order docstring 참고 — 취소는 '지금 이 주문' 하나만 없앤다).
# 그래서 "취소해 둔 상태를 유지하고 싶다"는 요구를 만족시키려면 재주문 자체를 끄는
# 스위치가 필요하다.
#
# 왜 파일인가: 자동매매가 두 프로세스로 갈려 있다(메인=real v8, run_mock.py=mock fire).
# Flask가 메모리 플래그를 켜도 모의 프로세스에는 닿지 않고, 재시작하면 사라진다.
# env_path()로 real/mock을 분리해 각 계좌의 스위치가 서로를 건드리지 않게 한다.
#
# ⚠️ 이 스위치는 **매수(신규 주문)만** 막는다. 청산(kiwoom_v8_exit / trailing_stop)과
#    대시보드 수동 매수/매도는 영향을 받지 않는다 — 보유 종목 보호가 꺼지면 안 된다.
_AUTOBUY_FLAG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kiwoom_autobuy.json')


def autobuy_flag_path(env: Optional[str] = None) -> str:
    return env_path(_AUTOBUY_FLAG, env)


def is_autobuy_enabled(env: Optional[str] = None) -> bool:
    """자동 재주문(자동매수)이 켜져 있는가. 파일이 없으면 True = 기존 동작.

    읽기 실패도 True 로 폴백한다. 스위치 파일이 깨졌다는 이유로 자동매매가 조용히
    멈추는 쪽이 더 위험하다(반대로 꺼진 걸 못 읽어 한 주기 더 주문이 나가는 건
    사용자가 화면에서 바로 알아챌 수 있다).
    """
    try:
        with open(autobuy_flag_path(env), 'r', encoding='utf-8') as f:
            return bool(json.load(f).get('enabled', True))
    except FileNotFoundError:
        return True
    except Exception:
        return True


def set_autobuy_enabled(enabled: bool, env: Optional[str] = None,
                        who: str = 'dashboard') -> Dict:
    state = {'enabled': bool(enabled), 'who': who,
             'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    path = autobuy_flag_path(env)
    tmp = '%s.tmp.%d' % (path, os.getpid())
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False)
    os.replace(tmp, path)
    return state


def get_trading_logger(name: str) -> 'logging.Logger':
    """자동매매 모듈 공용 파일 로거. `trading.log`(real) / `trading_mock.log`(mock)에 쓴다.

    2026-08-24 도입 — kiwoom_v8_strategy / kiwoom_v8_exit 가 `logging.getLogger(name)`만
    하고 핸들러를 붙이지 않아, `__main__`이 아닌 스케줄러 경로(run.py)에서는 INFO 로그가
    핸들러 없는 로거로 사라지고 있었다(2026-08-19 v8 가동 이후 5일간 trading.log에 v8
    관련 줄이 0건). 이 헬퍼로 kiwoom_trailing_stop.py 와 동일한 파일·포맷·로테이션 정책을
    강제해, 새 모듈이 같은 실수를 반복하지 않게 한다.

    이름별로 로거가 다르되(모듈 구분은 %(name)s 없이도 메시지 접두어로 이미 구분됨) 같은
    파일에 append 하므로, 여러 모듈이 호출해도 핸들러가 중복 추가되지 않는다
    (logger.handlers 가 비어 있을 때만 붙인다 — 표준 idempotent 패턴).
    """
    os.makedirs(_TRADING_LOG_DIR, exist_ok=True)
    log = logging.getLogger(name)
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    log.propagate = False   # 앱 root/waitress 로거로 전파 안 함 (logs/app 쪽에 중복 기록 방지)
    # 2026-09-11: 파일이 real/mock으로 나뉘어도 로그 한 줄만 떼어보면(복사/공유 시) 어느
    # 계좌인지 알 수 없다는 지적 — kiwoom_trailing_stop.py의 수동 로거와 동일하게 포맷 자체에
    # 환경 태그를 박는다.
    formatter = logging.Formatter(f'%(asctime)s [%(levelname)s][{KIWOOM_ENV.upper()}] %(message)s')

    # real -> trading.log (기존 파일 그대로, 180일 백업 이력 연속성 유지) / mock -> trading_mock.log
    log_name = 'trading.log' if KIWOOM_ENV == 'real' else f'trading_{KIWOOM_ENV}.log'
    from concurrent_log_handler import ConcurrentTimedRotatingFileHandler
    file_handler = ConcurrentTimedRotatingFileHandler(
        os.path.join(_TRADING_LOG_DIR, log_name), when='midnight', backupCount=180, encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    log.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    log.addHandler(console_handler)
    return log

# 호출 간격. 2026-08-19 ka10001(현재가) 로 실측한 값이다.
#
#   설정      목표건/초    429 발생    실효건/초
#   0.0556      18.0         2          6.0
#   0.1000      10.0         1          6.8
#   0.1429       7.0         0          6.3
#   0.2000       5.0         0          4.9
#
# 문서에는 계좌·토큰당 20건/초로 적혀 있지만 실제로는 10건/초에서도 429가 났다.
# 그리고 429 백오프 재시도(_call 의 _max_429_retries) 비용 때문에 **실효 처리량은
# 어느 설정에서든 6~7건/초에서 수렴**한다 — 18건/초로 설정해도 실효 6.0건/초로,
# 7건/초 설정(6.3건/초)보다 오히려 낮다. 더 밀어붙이는 게 순손실이다.
# 그래서 429 가 나지 않는 최대치인 7건/초를 쓴다.
#
# ⚠️ 프로세스 전역 간격이다. 트레일링 청산·계좌현황·대시보드·v8 이 이 예산을 공유한다.
#    한 계좌에 여러 프로세스를 동시에 붙이면 합산이 한도를 넘으므로 더 낮춰야 한다.
# 참고: 이전 값은 0.35초(2.86건/초)로, 근거 주석 없이 보수적으로 잡혀 있었다.
_RATE_LIMIT_SLEEP = 1.0 / 7.0  # ≈0.143초


def _get_token(env: Optional[str] = None) -> str:
    return os.environ.get(_cfg_for(env)['token_env'], '')


# ── 토큰 재발급 동시요청 방지 (2026-09-05) ──────────────────────────────────
# waitress가 스레드 24개로 돌아서, 대시보드 탭 하나 열 때 여러 스레드가 동시에 kt00018/
# ka10099/kt00001/ka10075 등을 호출한다. 이 시점에 토큰이 무효하면 각 스레드가 각자
# _refresh_token()을 불렀는데, 토큰 발급(au10001) 자체가 데이터 조회보다 훨씬 엄격하게
# 제한돼 있어(실측: "1700 허용된 API 요청 개수를 초과" 연발) 하나만 성공하고 나머지는
# 429로 실패 — 그 요청들의 조회 자체가 통째로 실패했다(fn_au10001은 실패 시 재시도 없이
# 바로 예외를 던진다). env별 락 + 쿨다운으로 동시 발급 시도를 한 번으로 합친다.
_TOKEN_REFRESH_LOCKS: Dict[str, threading.Lock] = {}
_TOKEN_REFRESH_LOCKS_GUARD = threading.Lock()
_TOKEN_LAST_REFRESH: Dict[str, float] = {}
_TOKEN_REFRESH_COOLDOWN = 5.0  # 초. 토큰 유효기간(24시간)에 비해 여러 자릿수 작은 값이라
                                # 진짜 만료 갱신을 막을 일은 없고, 동시 요청만 걸러낸다.


def _token_refresh_lock(key: str) -> threading.Lock:
    with _TOKEN_REFRESH_LOCKS_GUARD:
        lock = _TOKEN_REFRESH_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _TOKEN_REFRESH_LOCKS[key] = lock
        return lock


def _refresh_token(env: Optional[str] = None):
    key = env or KIWOOM_ENV
    lock = _token_refresh_lock(key)
    with lock:
        # 락을 기다리는 동안 다른 스레드가 이미 갱신했으면(쿨다운 이내) 재요청하지 않고
        # 그 결과(os.environ에 반영된 새 토큰)를 그대로 재사용한다.
        if time.time() - _TOKEN_LAST_REFRESH.get(key, 0.0) < _TOKEN_REFRESH_COOLDOWN:
            return
        from auto_trading.renew_kiwoom_token import fn_au10001
        c = _cfg_for(env)
        params = {
            'grant_type': 'client_credentials',
            'appkey': os.environ.get(c['app_key_env']),
            'secretkey': os.environ.get(c['secret_key_env']),
        }
        fn_au10001(data=params, host=c['base_url'], token_env_key=c['token_env'])
        _TOKEN_LAST_REFRESH[key] = time.time()


# 30초 트레일링 스탑 잡, 5분 계좌현황 잡, 대시보드 페이지 로드 등 서로 다른 스레드가
# 동시에 호출할 수 있어 호출별 sleep만으로는 부족함 — 프로세스 전체에서 호출 간격을 보장.
_rate_lock = threading.Lock()
_last_call_ts = 0.0


def _rate_limit_wait():
    global _last_call_ts
    with _rate_lock:
        wait = _RATE_LIMIT_SLEEP - (time.time() - _last_call_ts)
        if wait > 0:
            time.sleep(wait)
        _last_call_ts = time.time()


def _is_invalid_token_response(resp) -> bool:
    """키움은 토큰 만료를 HTTP 401이 아니라 200 + return_code!=0 (인증 실패 메시지)으로 내려줄 때가 있다.
    그대로 두면 숫자 필드가 전부 조용히 0으로 파싱되므로 반드시 걸러내야 함."""
    if resp.status_code != 200:
        return False
    try:
        data = resp.json()
    except ValueError:
        return False
    return data.get('return_code') not in (0, None) and '인증' in str(data.get('return_msg', ''))


def _call_raw(api_id: str, endpoint: str, body: dict,
              cont_yn: str = 'N', next_key: str = '', _max_429_retries: int = 3,
              env: Optional[str] = None):
    """_call()과 동일하지만 (json, response.headers)를 함께 반환한다.

    페이지네이션(연속조회)이 필요한 곳(kt00007 등)은 응답 헤더의 cont-yn/next-key를
    읽어야 다음 페이지를 요청할 수 있는데, _call()은 json 본문만 반환해 그 정보를 버린다.
    """
    url = _cfg_for(env)['base_url'] + endpoint
    headers = {
        'Content-Type': 'application/json;charset=UTF-8',
        'authorization': f'Bearer {_get_token(env)}',
        'cont-yn': cont_yn,
        'next-key': next_key,
        'api-id': api_id,
    }

    for attempt in range(_max_429_retries + 1):
        _rate_limit_wait()
        resp = requests.post(url, headers=headers, json=body, timeout=10)

        if resp.status_code == 401 or _is_invalid_token_response(resp):
            _refresh_token(env)
            headers['authorization'] = f'Bearer {_get_token(env)}'
            _rate_limit_wait()
            resp = requests.post(url, headers=headers, json=body, timeout=10)

        if resp.status_code == 429 and attempt < _max_429_retries:
            wait_s = 0.5 * (attempt + 1)
            ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]  # 밀리초 포함 (2026-09-03: time.strftime엔 밀리초가 없어서 누락돼 있었다)
            print(f'{ts} [WARN] 429 rate limit ({api_id}), {wait_s:.1f}s 후 재시도 ({attempt + 1}/{_max_429_retries})')
            time.sleep(wait_s)
            continue

        resp.raise_for_status()
        return resp.json(), resp.headers


def _call(api_id: str, endpoint: str, body: dict,
          cont_yn: str = 'N', next_key: str = '', _max_429_retries: int = 3,
          env: Optional[str] = None) -> dict:
    """키움 REST API 공통 호출. 401(또는 200+인증실패 응답) 시 토큰 재발급 후 1회 재시도, 429 시 백오프 재시도.

    env로 호출 대상 환경(mock/real)을 지정할 수 있다. None이면 프로세스 기본값.
    ⚠️ _rate_limit_wait()은 **환경과 무관한 프로세스 전역 예산**이다. 대시보드가 두 계좌를
       동시에 조회하면 그만큼 호출이 늘어 자동매매 쪽 처리량을 잠식한다(상단 _RATE_LIMIT_SLEEP 주석).
    """
    data, _ = _call_raw(api_id, endpoint, body, cont_yn, next_key, _max_429_retries, env)
    return data


# ── 현재가 조회 ──────────────────────────────────────────────────────────────

def get_current_price_and_name(stk_cd: str, env: Optional[str] = None) -> Tuple[int, str]:
    """(현재가(원), 종목명) 반환. 실패 시 (0, '')."""
    try:
        data = _call('ka10001', '/api/dostk/stkinfo', {'stk_cd': stk_cd}, env=env)
        raw = data.get('cur_prc', '0')
        price = abs(int(str(raw).replace(',', '').replace('+', '').replace('-', '')))
        return price, data.get('stk_nm', '') or ''
    except Exception as e:
        print(f'[ERROR] get_current_price_and_name {stk_cd}: {e}')
        return 0, ''


def get_current_price(stk_cd: str) -> int:
    """현재가(원) 반환. 실패 시 0."""
    return get_current_price_and_name(stk_cd)[0]


# 2026-10-05 실측(ka10095 관심종목정보요청, /api/dostk/stkinfo): stk_cd에 '005930|000660'처럼 '|'로
# 이어 보내면 한 번에 받는다. 100종목까지 되고(101개는 응답에 atn_stk_infr 자체가 없음) 100종목도
# 0.14초 — 단건(ka10001)을 종목 수만큼 부르던 것(레이트리밋으로 약 0.15초×N)을 1회로 줄인다.
# 응답은 요청 순서 그대로이고, 없는 종목코드는 stk_cd/cur_prc가 빈 문자열인 행으로 온다.
# cur_prc엔 전일 대비 부호(+/-)가 붙어 있어 abs 처리한다(ka10001과 같다 — 단건과 값 일치 확인).
_BULK_PRICE_MAX = 100


def get_current_prices(stk_cds: List[str], env: Optional[str] = None) -> Dict[str, int]:
    """종목코드들의 현재가(원)를 한 번에 조회해 {코드: 가격}으로 반환. 조회 실패·없는 종목은 빼고 돌려준다.
    100종목씩 나눠 호출하고, 한 묶음이 실패해도 나머지는 계속한다."""
    codes = []
    for c in stk_cds:
        c = (c or '').strip()
        if c and c not in codes:
            codes.append(c)
    out: Dict[str, int] = {}
    for i in range(0, len(codes), _BULK_PRICE_MAX):
        chunk = codes[i:i + _BULK_PRICE_MAX]
        try:
            data = _call('ka10095', '/api/dostk/stkinfo', {'stk_cd': '|'.join(chunk)}, env=env)
        except Exception as e:
            print(f'[ERROR] get_current_prices {len(chunk)}종목: {e}')
            continue
        for code, row in zip(chunk, data.get('atn_stk_infr') or []):   # 요청 순서 = 응답 순서
            raw = str(row.get('cur_prc') or '').replace(',', '').replace('+', '').replace('-', '')
            if raw.isdigit() and int(raw) > 0:
                out[code] = int(raw)
    return out


# ── 종목 상태(투자경고/관리종목/거래정지 등) 조회 (ka10099) ─────────────────────
# 2026-09-02 실측: ka10001엔 이 정보가 없다. ka10099(mrkt_tp='0' 코스피/'10' 코스닥)의
# 응답 list[].auditInfo 가 '정상'/'거래정지'/'관리종목'/'투자주의환기종목'/'투자경고'/
# '단기과열'/'투자주의' 중 하나로 온다(코스피+코스닥 합쳐 4,307종목 기준 실측 분포:
# 정상 4021, 거래정지 123, 관리종목 92, 투자주의환기종목 36, 투자경고 15, 단기과열 10,
# 투자주의 10). '정리매매'/'불성실공시'는 이 API에 없다 — 필요하면 별도 KRX 스크래핑이
# 필요하다(update_kor_stocks_by_xls.py와 같은 패턴).
_AUDIT_INFO_CACHE_LOCK = threading.Lock()
_AUDIT_INFO_CACHE: Optional[Tuple[float, Dict[str, str]]] = None
_AUDIT_INFO_CACHE_TTL = 300.0  # 5분. 계좌별이 아니라 시장 전체 공통 정보라 env 무관하게 캐시.


def get_stock_audit_info_map(env: Optional[str] = None, force: bool = False) -> Dict[str, str]:
    """전 종목 {종목코드: auditInfo} 맵. 5분 캐시(프로세스 전역, env 무관 — 시장 데이터는
    계좌와 상관없이 동일하다). 실패해도 예외를 던지지 않고 빈 dict를 돌려준다(호출부가
    보유종목 배지 표시용으로만 쓰므로, 실패해도 화면이 죽지 않는 쪽이 안전하다)."""
    global _AUDIT_INFO_CACHE
    now = time.time()
    with _AUDIT_INFO_CACHE_LOCK:
        if not force and _AUDIT_INFO_CACHE is not None and now - _AUDIT_INFO_CACHE[0] < _AUDIT_INFO_CACHE_TTL:
            return _AUDIT_INFO_CACHE[1]

    result: Dict[str, str] = {}
    try:
        for mrkt_tp in ('0', '10'):  # 0=코스피, 10=코스닥
            data = _call('ka10099', '/api/dostk/stkinfo', {'mrkt_tp': mrkt_tp}, env=env)
            for item in data.get('list') or []:
                code = item.get('code')
                audit = item.get('auditInfo')
                if code and audit:
                    result[code] = audit
    except Exception as e:
        print(f'[ERROR] get_stock_audit_info_map: {e}')
        with _AUDIT_INFO_CACHE_LOCK:
            if _AUDIT_INFO_CACHE is not None:
                return _AUDIT_INFO_CACHE[1]  # 이전 캐시라도 있으면 그걸 반환
        return {}

    with _AUDIT_INFO_CACHE_LOCK:
        _AUDIT_INFO_CACHE = (now, result)
    return result


_INDEX_CACHE_LOCK = threading.Lock()
_INDEX_CACHE: Optional[Tuple[float, Dict[str, Dict]]] = None
_INDEX_CACHE_TTL = 60.0  # 1분. 계좌별이 아니라 시장 전체 공통 정보라 env 무관하게 캐시.
_INDEX_CODES = {'kospi': '001', 'kosdaq': '101'}  # ka20001 inds_cd. mrkt_tp는 실측상 결과에 영향 없어 '0' 고정.


def get_market_index_rates(env: Optional[str] = None, force: bool = False) -> Dict[str, Dict]:
    """코스피/코스닥 종합지수 현재가·전일대비·등락률. 1분 캐시(프로세스 전역, env 무관).
    2026-09-04 mock 실응답으로 endpoint/파라미터 확인: ka20001 /api/dostk/sect,
    {'mrkt_tp': '0', 'inds_cd': '001'|'101'} → {cur_prc, pred_pre, flu_rt, ...}(부호 포함 문자열).
    실패해도 예외를 던지지 않고 이전 캐시(또는 빈 dict)를 반환한다(표시용이라 화면이 죽으면 안 됨)."""
    global _INDEX_CACHE
    now = time.time()
    with _INDEX_CACHE_LOCK:
        if not force and _INDEX_CACHE is not None and now - _INDEX_CACHE[0] < _INDEX_CACHE_TTL:
            return _INDEX_CACHE[1]

    result: Dict[str, Dict] = {}
    try:
        for name, inds_cd in _INDEX_CODES.items():
            data = _call('ka20001', '/api/dostk/sect', {'mrkt_tp': '0', 'inds_cd': inds_cd}, env=env)
            result[name] = {
                'price': _to_number(data.get('cur_prc')),
                'change': _to_number(data.get('pred_pre')),
                'rate': _to_number(data.get('flu_rt')) / 100.0,
            }
    except Exception as e:
        print(f'[ERROR] get_market_index_rates: {e}')
        with _INDEX_CACHE_LOCK:
            if _INDEX_CACHE is not None:
                return _INDEX_CACHE[1]
        return result

    with _INDEX_CACHE_LOCK:
        _INDEX_CACHE = (now, result)
    return result


_FX_CACHE_LOCK = threading.Lock()
_FX_CACHE: Optional[Tuple[float, float]] = None
_FX_CACHE_TTL = 60.0  # 1분. 코스피/코스닥 지수와 같은 캐시 주기 — 계좌 무관 공통 정보.
_FX_URL = ('https://m.search.naver.com/p/csearch/content/qapirender.nhn'
           '?key=calculator&pkid=141&q=%ED%99%98%EC%9C%A8&where=m'
           '&u1=keb&u6=standardUnit&u7=0&u3=USD&u4=KRW&u8=down&u2=1')


def get_usd_krw_rate(force: bool = False) -> Optional[float]:
    """네이버 환율계산기 API로 원/달러 현재가를 가져온다(키움 API엔 환율 조회가 없음).
    AutoSales.py/utils.py get_usd_krw_rate()와 동일한 엔드포인트 — 그쪽에서 이미 운영 중인
    방식을 그대로 재사용. 1분 캐시, 실패해도 예외 없이 이전 캐시(또는 None)를 반환한다
    (표시용 부가 정보라 화면이 죽으면 안 됨)."""
    global _FX_CACHE
    now = time.time()
    with _FX_CACHE_LOCK:
        if not force and _FX_CACHE is not None and now - _FX_CACHE[0] < _FX_CACHE_TTL:
            return _FX_CACHE[1]

    try:
        data = requests.get(_FX_URL, timeout=5).json()
        rate = None
        for item in data.get('country', []):
            if item.get('currencyUnit') == '원':
                rate = float(str(item.get('value', '0')).replace(',', ''))
                break
    except Exception as e:
        print(f'[ERROR] get_usd_krw_rate: {e}')
        with _FX_CACHE_LOCK:
            if _FX_CACHE is not None:
                return _FX_CACHE[1]
        return None

    if rate is not None:
        with _FX_CACHE_LOCK:
            _FX_CACHE = (now, rate)
    return rate


def get_investor_trend(stk_cd: str, env: Optional[str] = None) -> Optional[Dict[str, float]]:
    """종목별 외국인/기관/개인 순매수(원). ka10059(종목별투자자기관별차트요청), 2026-09-08 확인.

    응답의 stk_invsr_orgn[0]이 가장 최근 거래일 값(당일 장중이면 당일 누적치로 보임).
    ⚠️ 2026-09-08 단위 정정: 처음엔 천원 단위로 보고 ×1000 했는데, 069540 실측(관심종목
    추천 화면에서 "외국인 순매수 4백만원"으로 나온 게 이상해서 재검증)으로 틀렸다고 확인됨.
    acc_trde_prica(누적거래대금)를 acc_trde_qty×현재가로 역산하면(삼성전자 기준
    18,314,016주×270,000원≈4.94조 vs acc_trde_prica=4,900,114) **백만원 단위(×1,000,000)라야
    맞는다** — 천원 단위(×1,000)로는 1000배 작게 나온다(49억원). unit_tp='1' 파라미터명이
    "천주/천원"을 암시해서 잘못 짚었던 것으로 보인다. 실제 amt_qty_tp='1'(금액모드) 응답은
    unit_tp 값과 무관하게 백만원 단위로 보인다. 여기선 원 단위로 환산해서 반환한다.
    실패하면 None(표시용 부가 데이터라 호출부가 조용히 생략할 수 있게).

    ⚠️ 2026-09-22: foreign/institution 개별 필드는 raw 값이 없거나 빈 문자열이면 0이 아니라
    None을 반환한다 — 실측(관심종목 추천 이력)으로 특정 5분 사이클에서 그 순간 조회된 종목
    전부(12종목 전수)가 수억~수백억원 → 0 → 수억~수백억원으로 동시에 튀는 현상이 확인됐다.
    한 종목만 그런 게 아니라 그 사이클 전체가 그랬다는 건 실제 수급이 순간 0이 된 게 아니라
    ka10059가 그 순간 빈 응답을 준 것이라는 뜻 — _to_number()가 파싱 실패를 조용히 0.0으로
    돌려버려서(범용 헬퍼라 여기 맞춰 바꾸면 다른 호출부에 영향) '진짜 수급 0'과 '이번엔 못
    받음'이 구분이 안 됐다. 호출부(job/interest_stock_picks.py)가 None을 직전 정상값으로
    대체할 수 있게, 여기서부터 구분해서 넘긴다."""
    def _num_or_none(raw):
        if raw is None or str(raw).strip() == '':
            return None
        return _to_number(raw) * 1_000_000

    try:
        data = _call('ka10059', '/api/dostk/stkinfo', {
            'dt': datetime.now().strftime('%Y%m%d'),
            'stk_cd': stk_cd,
            'amt_qty_tp': '1',   # 1=금액
            'trde_tp': '0',      # 0=순매수
            'unit_tp': '1',      # 1=천주/천원(명목상) — 실측상 금액 필드는 백만원 단위로 옴
        }, env=env)
        rows = data.get('stk_invsr_orgn') or []
        if not rows:
            return None
        latest = rows[0]
        return {
            'date': latest.get('dt'),
            'foreign': _num_or_none(latest.get('frgnr_invsr')),
            'institution': _num_or_none(latest.get('orgn')),
            'individual': _num_or_none(latest.get('ind_invsr')),
        }
    except Exception as e:
        print(f'[WARN] get_investor_trend 실패: {stk_cd} {e}')
        return None


def get_intraday_range(stk_cd: str) -> Optional[Tuple[int, int, int]]:
    """(현재가, 당일 고가, 당일 저가) 반환. 실패하거나 값이 이상하면 None.

    kiwoom_fire_strategy_mock의 '종가위치' 필터용. 값에 +/- 부호와 콤마가 섞여 오므로 정규화한다.
    """
    try:
        data = _call('ka10001', '/api/dostk/stkinfo', {'stk_cd': stk_cd})

        def num(key):
            raw = str(data.get(key, '0')).replace(',', '').replace('+', '').replace('-', '')
            return abs(int(raw or 0))

        cur, high, low = num('cur_prc'), num('high_pric'), num('low_pric')
        if cur <= 0 or high <= 0 or low <= 0 or high < low:
            return None
        return cur, high, low
    except Exception as e:
        print(f'[ERROR] get_intraday_range {stk_cd}: {e}')
        return None


# ── 계좌 잔고 조회 ───────────────────────────────────────────────────────────

def get_balance(acnt_no: str, acnt_pwd: str) -> dict:
    """⚠️ 죽은 코드다. ka10007 은 /api/dostk/acnt 에서 지원하지 않는다
    (2026-08-21 실측: `1504:해당 URI에서는 지원하는 API ID가 아닙니다`).
    예수금이 필요하면 아래 get_deposit() 을 쓸 것."""
    body = {
        'acnt_no': acnt_no,
        'acnt_pwd': acnt_pwd,
        'qry_tp': '1',
        'dmst_stex_tp': 'KRX',
    }
    return _call('ka10007', '/api/dostk/acnt', body)


# ── 예수금 상세 (kt00001) ────────────────────────────────────────────────────
# 2026-08-21 추가. kt00018(계좌평가잔고)에는 **예수금 필드가 아예 없어서**, 그동안
# `보유현금 = 추정예탁자산 - 총평가금액` 으로 근사하고 있었다. 그 근사식이 계좌가 거의
# full 투자 상태가 되면 부호까지 뒤집힌다 — 추정예탁자산(prsm_dpst_aset_amt)은
# '예수금+평가금액'이 아니라 결제·비용을 반영한 추정치이기 때문이다.
# 실측 사고(2026-08-20 모의계좌): 추정예탁자산 27,939,203 - 총평가 28,155,600 = -216,397 로
# 대시보드 '보유 현금'이 음수로 표시됐다.
def get_deposit(acnt_no: str, acnt_pwd: str, env: Optional[str] = None) -> Dict:
    """예수금/주문가능금액. 한국 주식은 매수대금이 T+2 에 결제되므로 세 값이 다 다르다.

      entr          예수금        — 결제 전 기준. 오늘 매수한 대금이 아직 안 빠져 있다
      profa_ch      증거금현금(매수증거금) — 예수금 중 지금 당장 추가 매수엔 못 쓰는 부분.
                    실측(2026-09-16): entr - profa_ch == ord_alow_amt 로 정확히 맞아떨어짐
                    (932,902 - 569,674 = 363,228) — 미체결 매수 주문이 하나도 없을 때도
                    0이 아니었다(569,674원). 즉 미체결 주문 증거금뿐 아니라 **오늘 체결된
                    매매의 결제 전(T+2) 대금**도 여기 잡히는 것으로 보인다(2026-09-16
                    사용자 요청으로 추가 — kt00001 원본에는 있었는데 그동안 파싱을 안 했다).
      ord_alow_amt  주문가능금액   — **지금 더 살 수 있는 돈.** 사이징·표시에 쓸 값
      pymn_alow_amt 출금가능금액   — 실제로 뺄 수 있는 돈
      d2_entra      D+2 추정예수금 — 결제 완료 후 예수금. 음수면 미수금이다

    ord_alow_amt 가 음수면 예수금을 초과해 주문한 것이다(미수).
    """
    body = {'acnt_no': acnt_no, 'acnt_pwd': acnt_pwd, 'qry_tp': '1'}
    data = _call('kt00001', '/api/dostk/acnt', body, env=env)
    if data.get('return_code') not in (0, None):
        raise RuntimeError(f'kt00001 응답 오류: {data.get("return_msg")} '
                           f'(return_code={data.get("return_code")})')
    return {
        'entr': _to_number(data.get('entr')),
        'profa_ch': _to_number(data.get('profa_ch')),
        'ord_alow_amt': _to_number(data.get('ord_alow_amt')),
        'pymn_alow_amt': _to_number(data.get('pymn_alow_amt')),
        'd1_entra': _to_number(data.get('d1_entra')),
        'd2_entra': _to_number(data.get('d2_entra')),
    }


# ── 보유 종목별 평가 (계좌평가잔고내역요청, kt00018) ──────────────────────────
# 모의투자 실응답으로 검증 완료 (2026-07-13).
HOLDING_LIST_KEY = 'acnt_evlt_remn_indv_tot'   # 응답 중 종목별 리스트가 들어있는 키
FIELD_STK_CD = 'stk_cd'          # 종목코드 (값에 'A' 접두사 포함, 예: "A005930" → 아래에서 제거)
FIELD_STK_NM = 'stk_nm'          # 종목명
FIELD_QTY = 'rmnd_qty'           # 보유수량
FIELD_AVG_PRICE = 'pur_pric'     # 매입가(평균단가)
FIELD_CUR_PRICE = 'cur_prc'      # 현재가
FIELD_PROFIT_RATE = 'prft_rt'    # 수익률(%) — evltv_prft_rt 아님, evltv_prft(손익금액)와 혼동 주의
FIELD_PROFIT_AMOUNT = 'evltv_prft'  # 평가손익금액(원). (cur_price-avg_price)*qty로 재계산하면 매입가 원단위 반올림 때문에 tot_evlt_pl 합계와 오차가 생겨 반드시 이 필드를 그대로 써야 함
FIELD_PRED_CLOSE = 'pred_close_pric'  # 전일종가. 매입가 기준 수익률(prft_rt)과 달리 '오늘' 등락만 보려면 이 값 기준이어야 함
FIELD_SUM_CMSN = 'sum_cmsn'     # 매수+매도(추정) 수수료 합계(원). 지금 전량 매도한다고 가정한 추정치
FIELD_TAX = 'tax'               # 매도세(추정, 원). sum_cmsn과 마찬가지로 전량 매도 가정
# 2026-09-01 발견: evltv_prft(=pnl 필드)는 이미 sum_cmsn+tax를 뺀 순손익이고 prft_rt도 그
# 순손익 기준이라, (cur_price-avg_price)*qty로 직접 재계산한 값과 항상 어긋난다(수수료+세금분,
# 매입금액 대비 대략 0.8~0.9%). 호출부가 부분 수량만 팔 때 비례 배분할 수 있도록 여기서
# est_fee(총 보유수량 기준 수수료+세금 추정 합계)를 그대로 노출한다.


def dump_holdings_raw(acnt_no: str, acnt_pwd: str, env: Optional[str] = None) -> dict:
    """모의투자 응답 원본 확인용. 필드명 검증 후에는 get_holdings()만 쓰면 됨.

    2026-09-03: env를 안 받아서 acnt_no/acnt_pwd를 mock으로 넘겨도 프로세스 기본
    KIWOOM_ENV(대개 real)로 호출되는 버그가 있었다 — 계좌번호와 실제 조회 대상 환경이
    어긋나 엉뚱한(다른 env의) 계좌 데이터가 반환됐다. env 파라미터를 추가해 명시적으로
    지정할 수 있게 했다."""
    body = {'acnt_no': acnt_no, 'acnt_pwd': acnt_pwd, 'qry_tp': '1', 'dmst_stex_tp': 'KRX'}
    data = _call('kt00018', '/api/dostk/acnt', body, env=env)
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return data


def _to_number(raw, default=0.0) -> float:
    try:
        return float(str(raw).replace(',', '').replace('%', '').strip())
    except (TypeError, ValueError):
        return default


def _fetch_kt00018(acnt_no: str, acnt_pwd: str, env: Optional[str] = None) -> dict:
    body = {'acnt_no': acnt_no, 'acnt_pwd': acnt_pwd, 'qry_tp': '1', 'dmst_stex_tp': 'KRX'}
    return _call('kt00018', '/api/dostk/acnt', body, env=env)


def _parse_holdings(data: dict) -> List[Dict]:
    rows = data.get(HOLDING_LIST_KEY, [])
    if not isinstance(rows, list):
        print(f'[WARN] get_holdings: "{HOLDING_LIST_KEY}" 키가 없거나 형식이 다름. 응답: {data}')
        return []

    holdings = []
    for row in rows:
        qty = int(_to_number(row.get(FIELD_QTY)))
        if qty <= 0:
            continue
        avg_price = _to_number(row.get(FIELD_AVG_PRICE))
        cur_price = _to_number(row.get(FIELD_CUR_PRICE))
        profit_rate = _to_number(row.get(FIELD_PROFIT_RATE)) / 100.0
        pnl = _to_number(row.get(FIELD_PROFIT_AMOUNT))
        pred_close = _to_number(row.get(FIELD_PRED_CLOSE))
        est_fee = _to_number(row.get(FIELD_SUM_CMSN)) + _to_number(row.get(FIELD_TAX))
        if avg_price <= 0:
            print(f'[WARN] get_holdings: 매입가 파싱 실패 stk_cd={row.get(FIELD_STK_CD)} row={row}')
            continue
        # API가 제공하는 손익률이 비정상(0 등)이면 직접 계산으로 보정
        if profit_rate == 0.0 and cur_price > 0:
            profit_rate = (cur_price - avg_price) / avg_price
        if pnl == 0.0 and cur_price > 0:
            pnl = (cur_price - avg_price) * qty
        # 매입가 기준 수익률(profit_rate)과는 별개로, '오늘' 하루치 등락만 보려면 전일종가 기준이어야 함
        day_change_rate = (cur_price - pred_close) / pred_close if pred_close > 0 else None

        raw_stk_cd = row.get(FIELD_STK_CD) or ''
        stk_cd = raw_stk_cd[1:] if raw_stk_cd.startswith('A') else raw_stk_cd

        holdings.append({
            'stk_cd': stk_cd,
            'stk_nm': row.get(FIELD_STK_NM),
            'qty': qty,
            'avg_price': avg_price,
            'cur_price': cur_price,
            'profit_rate': profit_rate,
            'pnl': pnl,
            'day_change_rate': day_change_rate,
            'pred_close': pred_close,  # 2026-09-02: kt00018 pred_close_pric 원본. 호출부가
                                        # cur_price와 같은지(예전 결함 재발 여부) 스스로 검증할 수 있게 노출
            'est_fee': est_fee,  # 전량 매도 가정 수수료+세금 추정 합계(원). 부분매도 시 비례 배분해서 쓸 것
        })
    return holdings


def _parse_summary(data: dict) -> Dict:
    if data.get('return_code') not in (0, None):
        # 여기서 조용히 0을 반환하면 총자산=0으로 표시되고 일/주/월 손익 기준선까지 오염된다.
        raise RuntimeError(f'kt00018 응답 오류: {data.get("return_msg")} (return_code={data.get("return_code")})')
    return {
        'total_asset': _to_number(data.get('prsm_dpst_aset_amt')),  # 추정예탁자산(총 계좌 자산)
        'tot_pur_amt': _to_number(data.get('tot_pur_amt')),         # 총매입금액
        'tot_evlt_amt': _to_number(data.get('tot_evlt_amt')),       # 총평가금액(보유종목)
        'tot_evlt_pl': _to_number(data.get('tot_evlt_pl')),         # 총평가손익
        'tot_prft_rt': _to_number(data.get('tot_prft_rt')) / 100.0, # 총수익률
    }


def get_holdings(acnt_no: str, acnt_pwd: str, env: Optional[str] = None) -> List[Dict]:
    """
    보유 종목별 수량/평균단가/현재가/수익률을 한 번의 호출로 반환.
    반환: [{stk_cd, stk_nm, qty, avg_price, cur_price, profit_rate}, ...]
    profit_rate는 0.05 = +5% 형태(비율)로 정규화해서 반환.
    """
    return _parse_holdings(_fetch_kt00018(acnt_no, acnt_pwd, env))


def get_account_summary(acnt_no: str, acnt_pwd: str, env: Optional[str] = None) -> Dict:
    """
    계좌 총 자산/평가/손익 요약 (kt00018 재사용).
    total_asset = 추정예탁자산(예수금 + 보유종목 평가금액 합계 = 총 계좌 자산).
    """
    return _parse_summary(_fetch_kt00018(acnt_no, acnt_pwd, env))


def get_holdings_and_summary(acnt_no: str, acnt_pwd: str,
                             env: Optional[str] = None) -> Tuple[List[Dict], Dict]:
    """kt00018을 한 번만 호출해 보유종목·계좌요약을 함께 반환 (호출 횟수 절반으로)."""
    data = _fetch_kt00018(acnt_no, acnt_pwd, env)
    return _parse_holdings(data), _parse_summary(data)


# ── 보유중 배지용 종목코드 조회 (2026-09-14) ────────────────────────────────
# 관심종목/추천종목 화면(카드뷰·표)에 "지금 실전/모의 계좌에 보유 중"을 표시하기 위한
# 가벼운 조회. 계좌 조회(kt00018)는 API 호출이라 관심종목 화면에서 60초마다(즐겨찾기/
# 자동매수 동기화 주기와 같이 묶임) 두 계좌씩 부르면 낭비다 — 짧게 캐시해서 같은
# 주기 안의 중복 호출(여러 브라우저 탭 등)을 흡수한다. 실시간성이 중요한 값이 아니다
# (실제 보유 화면인 '내 계좌' 탭은 이 함수를 쓰지 않고 3초 주기로 직접 조회한다).
_owned_codes_cache_lock = threading.Lock()
_owned_codes_cache: Dict[str, Tuple[float, set]] = {}
_OWNED_CODES_CACHE_TTL = 5.0


def get_owned_codes(env: Optional[str] = None) -> set:
    """현재 보유 중인 종목코드 집합. 계좌 정보가 없거나 조회 실패하면 빈 집합(안전 폴백)."""
    key = env or KIWOOM_ENV
    now = time.time()
    with _owned_codes_cache_lock:
        cached = _owned_codes_cache.get(key)
        if cached is not None and now - cached[0] < _OWNED_CODES_CACHE_TTL:
            return cached[1]

    acnt_no, acnt_pwd = get_account_credentials(env)
    if acnt_no and acnt_pwd:
        try:
            codes = {h['stk_cd'] for h in get_holdings(acnt_no, acnt_pwd, env)}
        except Exception:
            codes = set()
    else:
        codes = set()

    with _owned_codes_cache_lock:
        _owned_codes_cache[key] = (now, codes)
    return codes


# ── 주문 ─────────────────────────────────────────────────────────────────────
# ⚠️ 매수(kt10000)/매도(kt10001) 별도 api-id, 필드명(ord_qty/ord_uv/trde_tp/dmst_stex_tp),
#    acnt_no/acnt_pwd 불필요(계좌는 토큰에 귀속) — 실제 매수 성공 예제(블로그)를 근거로 수정함.
#    실거래 전 반드시 모의투자로 1주만 직접 주문해서 정상 동작 확인할 것.

def place_order(stk_cd: str, qty: int, price: int,
                side: str, trde_tp: str = '3', dmst_stex_tp: str = 'KRX',
                env: Optional[str] = None) -> dict:
    """
    side         : '1' 매수(kt10000) / '2' 매도(kt10001)
    trde_tp      : '3' 시장가 (기본) / '0' 보통(지정가)
    price        : 지정가 주문 시 주문단가, 시장가는 0
    dmst_stex_tp : 'KRX'(기본) / 'NXT' / 'SOR'
    """
    body = {
        'dmst_stex_tp': dmst_stex_tp,
        'stk_cd': stk_cd,
        'ord_qty': str(qty),
        'ord_uv': str(price),
        'trde_tp': trde_tp,
    }
    api_id = 'kt10000' if side == '1' else 'kt10001'
    result = _call(api_id, '/api/dostk/ordr', body, env=env)
    # 로깅은 호출부 책임 — 여기서 print하면 호출부의 상세 로그(_log.info)와 항상 겹친다.
    # 단, kiwoom_trailing_stop.py의 손절/트레일링/정체보호 성공 로그는 result를 찍지 않으므로
    # ord_no를 그쪽 로그 문자열에 직접 넣어뒀다(2026-08-12) — 여기서 지우기 전에 확인할 것.
    return result


def cancel_order(orig_ord_no: str, stk_cd: str, qty: int = 0,
                 side: str = '1', dmst_stex_tp: str = 'KRX',
                 env: Optional[str] = None) -> dict:
    """주문 취소. qty=0 이면 잔량 전부 취소.
    api-id: kt10003(매수취소) / kt10004(매도취소). 2026-08-19 실계좌 확인."""
    body = {
        'dmst_stex_tp': dmst_stex_tp,
        'orig_ord_no': str(orig_ord_no),
        'stk_cd': stk_cd,
        'cncl_qty': str(qty) if qty else '0',
    }
    api_id = 'kt10003' if side == '1' else 'kt10004'
    return _call(api_id, '/api/dostk/ordr', body, env=env)


def buy_market(stk_cd: str, qty: int, dmst_stex_tp: str = 'KRX',
               env: Optional[str] = None) -> dict:
    return place_order(stk_cd, qty, 0, side='1', trde_tp='3', dmst_stex_tp=dmst_stex_tp, env=env)


def sell_market(stk_cd: str, qty: int, dmst_stex_tp: str = 'KRX',
                env: Optional[str] = None) -> dict:
    return place_order(stk_cd, qty, 0, side='2', trde_tp='3', dmst_stex_tp=dmst_stex_tp, env=env)


def sell_limit(stk_cd: str, qty: int, price: int, dmst_stex_tp: str = 'KRX',
               env: Optional[str] = None) -> dict:
    """지정가 매도. 2026-09-14 애프터마켓(16:00~20:00) 대응으로 추가.

    ⚠️ 이 시간대는 시장가(trde_tp='3')를 거부한다(실측: return_code 20,
    '[2000](521790:해당 호가유형은 주문 불가능한 시간입니다.)' — kiwoom_v8_exit.py의
    트레일링/샹들리에/익절/보유상한 청산이 전부 이 코드로 거부됐다). 지정가만 받는다.
    청산 로직은 즉시 체결을 원하므로 호출부(kiwoom_v8_exit._sell)가 현재가보다 살짝
    낮은 공격적 지정가를 계산해서 넘긴다 — 이 함수 자체는 가격을 보정하지 않는다."""
    return place_order(stk_cd, qty, price, side='2', trde_tp='0', dmst_stex_tp=dmst_stex_tp, env=env)


# ── 체결 조회 (ka10076) ──────────────────────────────────────────────────────
# 모의투자 실응답으로 검증 완료 (2026-08-12). 응답 구조:
#   {'cntr': [ {...}, ... ], 'return_code': 0, 'return_msg': ' 조회가 완료되었습니다.'}
# 항목 필드(전부 문자열):
#   ord_no        주문번호        ← place_order() 응답의 ord_no와 매칭되는 키
#   stk_cd        종목코드        (조회 응답에는 'A' 접두사가 없었으나 방어적으로 lstrip)
#   stk_nm        종목명
#   io_tp_nm      '+매수' / '-매도'
#   ord_qty       주문수량
#   ord_pric      주문단가        (시장가는 '0')
#   cntr_qty      체결수량        ★
#   cntr_pric     체결단가        ★
#   oso_qty       미체결수량      ★ 0이 아니면 부분체결
#   tdy_trde_cmsn 당일 매매수수료
#   tdy_trde_tax  당일 매매세금   (매수는 0, 매도에만 거래세)
#   ord_stt       주문상태        ('체결')
#   trde_tp       '시장가' / '보통'
#   ord_tm        주문시각        ('151822' = HHMMSS)
#   stex_tp/_txt  거래소구분      ('1'/'KRX')
# 주의: 날짜 파라미터가 없어 '당일분'만 돌려준다 → 소급 정산은 같은 날에만 가능하다.
#      (kt00007에 ord_dt가 있으나 모의투자에서 '해당조회내역이 없습니다'로 비어서 쓰지 않는다.)
CNTR_LIST_KEY = 'cntr'


def get_filled_orders(acnt_no: str, acnt_pwd: str, stk_cd: str = '', env: Optional[str] = None) -> List[Dict]:
    """당일 체결 내역(ka10076). stk_cd를 주면 그 종목만.

    반환: [{'ord_no','stk_cd','stk_nm','side','ord_qty','cntr_qty','oso_qty',
            'cntr_pric','cmsn','tax','ord_stt','ord_tm'}] — 숫자는 float/int로 변환됨.

    2026-09-03: env를 안 받아서 항상 프로세스 기본 KIWOOM_ENV로 조회되는 버그가 있었다 —
    acnt_no/acnt_pwd를 mock으로 넘겨도 프로세스가 real이면 실계좌 체결내역이 반환됐다
    (테스트 스크립트에서 발견, 상시 가동 스케줄러는 각자 자기 env로만 호출해 실질 영향은
    없었음). env 파라미터를 추가해 명시적으로 지정할 수 있게 했다.
    """
    body = {
        'acnt_no': acnt_no, 'acnt_pwd': acnt_pwd,
        'stk_cd': stk_cd, 'qry_tp': '0', 'sell_tp': '0', 'ord_no': '', 'stex_tp': '0',
    }
    data = _call('ka10076', '/api/dostk/acnt', body, env=env)
    out = []
    for r in (data.get(CNTR_LIST_KEY) or []):
        io = str(r.get('io_tp_nm') or '')
        out.append({
            'ord_no': str(r.get('ord_no') or '').strip(),
            'stk_cd': str(r.get('stk_cd') or '').lstrip('A'),
            'stk_nm': r.get('stk_nm'),
            'side': 'buy' if '매수' in io else ('sell' if '매도' in io else None),
            'ord_qty': int(_to_number(r.get('ord_qty'))),
            'cntr_qty': int(_to_number(r.get('cntr_qty'))),
            'oso_qty': int(_to_number(r.get('oso_qty'))),
            'cntr_pric': _to_number(r.get('cntr_pric')),
            'cmsn': _to_number(r.get('tdy_trde_cmsn')),
            'tax': _to_number(r.get('tdy_trde_tax')),
            'ord_stt': r.get('ord_stt'),
            'ord_tm': str(r.get('ord_tm') or ''),
        })
    return out


# ── 계좌별 주문체결내역상세 (kt00007) — 날짜 지정 소급 조회 ────────────────────
# 2026-08-24 실계좌로 검증 완료 (20260819/20260820/20260821, ord_dt별 각 9/30/30건).
# 기존 주석은 모의투자 테스트만 근거로 "안 씀"이라 적었으나 실계좌는 정상 동작한다.
# ka10076과 달리 ord_dt로 과거 날짜를 조회할 수 있어, v8 거래이력 소급 백필에 이 API를 쓴다.
def get_order_history(acnt_no: str, acnt_pwd: str, ord_dt: str,
                      env: Optional[str] = None) -> List[Dict]:
    """지정한 날짜(YYYYMMDD)의 주문/체결 내역 전체(페이지네이션 처리 포함).

    반환: [{'ord_no','stk_cd','stk_nm','side','ord_qty','cntr_qty','cntr_pric',
            'ord_tm'}] — cntr_qty=0인 항목은 미체결(취소/거부 포함)이니 실제 체결만
    보려면 cntr_qty>0으로 걸러야 한다.
    """
    body = {'acnt_no': acnt_no, 'acnt_pwd': acnt_pwd, 'ord_dt': ord_dt, 'qry_tp': '1',
            'stk_bond_tp': '0', 'sell_tp': '0', 'stk_cd': '', 'fr_ord_no': '',
            'dmst_stex_tp': 'KRX'}
    out = []
    cont_yn, next_key = 'N', ''
    for _ in range(50):   # 안전판 — 무한루프 방지
        data, headers = _call_raw('kt00007', '/api/dostk/acnt', body,
                                  cont_yn=cont_yn, next_key=next_key, env=env)
        for r in (data.get('acnt_ord_cntr_prps_dtl') or []):
            io = str(r.get('io_tp_nm') or '')
            out.append({
                'ord_no': str(r.get('ord_no') or '').strip(),
                'stk_cd': str(r.get('stk_cd') or '').lstrip('A'),
                'stk_nm': r.get('stk_nm'),
                'side': 'buy' if '매수' in io else ('sell' if '매도' in io else None),
                'ord_qty': int(_to_number(r.get('ord_qty'))),
                'cntr_qty': int(_to_number(r.get('cntr_qty'))),
                'cntr_pric': _to_number(r.get('cntr_uv')),
                'ord_tm': str(r.get('ord_tm') or ''),
            })
        cont_yn = headers.get('cont-yn', 'N')
        next_key = headers.get('next-key', '')
        if cont_yn != 'Y' or not next_key:
            break
    return out


_unfilled_cache_lock = threading.Lock()
_unfilled_cache: Dict[Optional[str], Tuple[float, List[Dict]]] = {}
_UNFILLED_CACHE_TTL = 2.0  # 초. 대시보드 자동새로고침(3초)보다 짧게 잡아, 거의 동시에
                            # 들어오는 /kiwoom/holdings + /kiwoom/orders 두 요청이 같은
                            # (acnt_no 고정, env만 다른) 조회를 중복 호출하지 않게 한다.
                            # v8 매매 루프(60초 주기)는 이 TTL보다 훨씬 뜸하게 부르므로
                            # 사실상 항상 캐시 미스 — 신선도에 영향 없다.


def get_unfilled_orders(acnt_no: str, acnt_pwd: str, env: Optional[str] = None) -> List[Dict]:
    """미체결 주문(ka10075). 응답 리스트 키는 'oso'. 시장가만 쓰는 동안은 보통 빈 리스트다.

    원본 키(ord_no/stk_cd/oso_qty/io_tp_nm 등, 값은 전부 문자열)는 v8_strategy가 그대로 쓰므로
    유지하고, 숫자로 바로 쓰기 편하게 *_num 필드만 덧붙인다. cur_prc는 원본에 +/- 부호가
    붙어 있어(전일대비 방향) cur_prc_num은 절대값으로 정규화한다.

    ⚠️ env(계좌 구분)당 최대 _UNFILLED_CACHE_TTL초 캐시된 값을 돌려줄 수 있다 — 호출 직후
    낸 주문이 바로 안 보일 수 있는 대신 API 호출 폭주를 막는다. acnt_no는 env당 고정이라
    캐시 키에서 뺐다.
    """
    now = time.time()
    with _unfilled_cache_lock:
        cached = _unfilled_cache.get(env)
        if cached is not None and now - cached[0] < _UNFILLED_CACHE_TTL:
            return cached[1]

    body = {
        'acnt_no': acnt_no, 'acnt_pwd': acnt_pwd,
        'all_stk_tp': '0', 'trde_tp': '0', 'stk_cd': '', 'stex_tp': '0',
    }
    data = _call('ka10075', '/api/dostk/acnt', body, env=env)
    rows = data.get('oso') or []
    for r in rows:
        r['cur_prc_num'] = abs(_to_number(r.get('cur_prc')))
        r['ord_pric_num'] = abs(_to_number(r.get('ord_pric')))
        r['ord_qty_num'] = int(_to_number(r.get('ord_qty')))
        r['oso_qty_num'] = int(_to_number(r.get('oso_qty')))

    with _unfilled_cache_lock:
        _unfilled_cache[env] = (now, rows)
    return rows
