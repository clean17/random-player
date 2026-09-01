import os
import time
import json
import logging
import threading
import requests
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
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')

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


def _refresh_token(env: Optional[str] = None):
    from auto_trading.renew_kiwoom_token import fn_au10001
    c = _cfg_for(env)
    params = {
        'grant_type': 'client_credentials',
        'appkey': os.environ.get(c['app_key_env']),
        'secretkey': os.environ.get(c['secret_key_env']),
    }
    fn_au10001(data=params, host=c['base_url'], token_env_key=c['token_env'])


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
            ts = time.strftime('%Y-%m-%d %H:%M:%S')
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


def dump_holdings_raw(acnt_no: str, acnt_pwd: str) -> dict:
    """모의투자 응답 원본 확인용. 필드명 검증 후에는 get_holdings()만 쓰면 됨."""
    body = {'acnt_no': acnt_no, 'acnt_pwd': acnt_pwd, 'qry_tp': '1', 'dmst_stex_tp': 'KRX'}
    data = _call('kt00018', '/api/dostk/acnt', body)
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


def get_filled_orders(acnt_no: str, acnt_pwd: str, stk_cd: str = '') -> List[Dict]:
    """당일 체결 내역(ka10076). stk_cd를 주면 그 종목만.

    반환: [{'ord_no','stk_cd','stk_nm','side','ord_qty','cntr_qty','oso_qty',
            'cntr_pric','cmsn','tax','ord_stt','ord_tm'}] — 숫자는 float/int로 변환됨.
    """
    body = {
        'acnt_no': acnt_no, 'acnt_pwd': acnt_pwd,
        'stk_cd': stk_cd, 'qry_tp': '0', 'sell_tp': '0', 'ord_no': '', 'stex_tp': '0',
    }
    data = _call('ka10076', '/api/dostk/acnt', body)
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
