import os
import time
import json
import threading
import requests
from typing import Dict, List, Tuple
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
BASE_URL = _cfg['base_url']


def get_account_credentials() -> tuple:
    """KIWOOM_ENV(mock/real)에 맞는 계좌번호/비밀번호를 반환. 모의·실전 계좌번호는 서로 다르므로
    호출부에서 acnt_no를 직접 .env 키로 읽지 말고 반드시 이 함수를 통해서만 가져올 것."""
    return os.environ.get(_cfg['acnt_no_env']), os.environ.get(_cfg['acnt_pwd_env'])

_RATE_LIMIT_SLEEP = 0.35  # 키움 초당 호출 제한 대응


def _get_token() -> str:
    return os.environ.get(_cfg['token_env'], '')


def _refresh_token():
    from auto_trading.renew_kiwoom_token import fn_au10001
    params = {
        'grant_type': 'client_credentials',
        'appkey': os.environ.get(_cfg['app_key_env']),
        'secretkey': os.environ.get(_cfg['secret_key_env']),
    }
    fn_au10001(data=params, host=_cfg['base_url'], token_env_key=_cfg['token_env'])


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


def _call(api_id: str, endpoint: str, body: dict,
          cont_yn: str = 'N', next_key: str = '', _max_429_retries: int = 3) -> dict:
    """키움 REST API 공통 호출. 401(또는 200+인증실패 응답) 시 토큰 재발급 후 1회 재시도, 429 시 백오프 재시도."""
    url = BASE_URL + endpoint
    headers = {
        'Content-Type': 'application/json;charset=UTF-8',
        'authorization': f'Bearer {_get_token()}',
        'cont-yn': cont_yn,
        'next-key': next_key,
        'api-id': api_id,
    }

    for attempt in range(_max_429_retries + 1):
        _rate_limit_wait()
        resp = requests.post(url, headers=headers, json=body, timeout=10)

        if resp.status_code == 401 or _is_invalid_token_response(resp):
            _refresh_token()
            headers['authorization'] = f'Bearer {_get_token()}'
            _rate_limit_wait()
            resp = requests.post(url, headers=headers, json=body, timeout=10)

        if resp.status_code == 429 and attempt < _max_429_retries:
            wait_s = 0.5 * (attempt + 1)
            print(f'[WARN] 429 rate limit ({api_id}), {wait_s:.1f}s 후 재시도 ({attempt + 1}/{_max_429_retries})')
            time.sleep(wait_s)
            continue

        resp.raise_for_status()
        return resp.json()


# ── 현재가 조회 ──────────────────────────────────────────────────────────────

def get_current_price_and_name(stk_cd: str) -> Tuple[int, str]:
    """(현재가(원), 종목명) 반환. 실패 시 (0, '')."""
    try:
        data = _call('ka10001', '/api/dostk/stkinfo', {'stk_cd': stk_cd})
        raw = data.get('cur_prc', '0')
        price = abs(int(str(raw).replace(',', '').replace('+', '').replace('-', '')))
        return price, data.get('stk_nm', '') or ''
    except Exception as e:
        print(f'[ERROR] get_current_price_and_name {stk_cd}: {e}')
        return 0, ''


def get_current_price(stk_cd: str) -> int:
    """현재가(원) 반환. 실패 시 0."""
    return get_current_price_and_name(stk_cd)[0]


# ── 계좌 잔고 조회 ───────────────────────────────────────────────────────────

def get_balance(acnt_no: str, acnt_pwd: str) -> dict:
    body = {
        'acnt_no': acnt_no,
        'acnt_pwd': acnt_pwd,
        'qry_tp': '1',
        'dmst_stex_tp': 'KRX',
    }
    return _call('ka10007', '/api/dostk/acnt', body)


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


def _fetch_kt00018(acnt_no: str, acnt_pwd: str) -> dict:
    body = {'acnt_no': acnt_no, 'acnt_pwd': acnt_pwd, 'qry_tp': '1', 'dmst_stex_tp': 'KRX'}
    return _call('kt00018', '/api/dostk/acnt', body)


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
        if avg_price <= 0:
            print(f'[WARN] get_holdings: 매입가 파싱 실패 stk_cd={row.get(FIELD_STK_CD)} row={row}')
            continue
        # API가 제공하는 손익률이 비정상(0 등)이면 직접 계산으로 보정
        if profit_rate == 0.0 and cur_price > 0:
            profit_rate = (cur_price - avg_price) / avg_price
        if pnl == 0.0 and cur_price > 0:
            pnl = (cur_price - avg_price) * qty

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


def get_holdings(acnt_no: str, acnt_pwd: str) -> List[Dict]:
    """
    보유 종목별 수량/평균단가/현재가/수익률을 한 번의 호출로 반환.
    반환: [{stk_cd, stk_nm, qty, avg_price, cur_price, profit_rate}, ...]
    profit_rate는 0.05 = +5% 형태(비율)로 정규화해서 반환.
    """
    return _parse_holdings(_fetch_kt00018(acnt_no, acnt_pwd))


def get_account_summary(acnt_no: str, acnt_pwd: str) -> Dict:
    """
    계좌 총 자산/평가/손익 요약 (kt00018 재사용).
    total_asset = 추정예탁자산(예수금 + 보유종목 평가금액 합계 = 총 계좌 자산).
    """
    return _parse_summary(_fetch_kt00018(acnt_no, acnt_pwd))


def get_holdings_and_summary(acnt_no: str, acnt_pwd: str) -> Tuple[List[Dict], Dict]:
    """kt00018을 한 번만 호출해 보유종목·계좌요약을 함께 반환 (호출 횟수 절반으로)."""
    data = _fetch_kt00018(acnt_no, acnt_pwd)
    return _parse_holdings(data), _parse_summary(data)


# ── 주문 ─────────────────────────────────────────────────────────────────────
# ⚠️ 매수(kt10000)/매도(kt10001) 별도 api-id, 필드명(ord_qty/ord_uv/trde_tp/dmst_stex_tp),
#    acnt_no/acnt_pwd 불필요(계좌는 토큰에 귀속) — 실제 매수 성공 예제(블로그)를 근거로 수정함.
#    실거래 전 반드시 모의투자로 1주만 직접 주문해서 정상 동작 확인할 것.

def place_order(stk_cd: str, qty: int, price: int,
                side: str, trde_tp: str = '3', dmst_stex_tp: str = 'KRX') -> dict:
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
    result = _call(api_id, '/api/dostk/ordr', body)
    # 로깅은 호출부 책임 — 여기서 print하면 호출부의 상세 로그(_log.info)와 항상 겹친다.
    # 단, kiwoom_trailing_stop.py의 손절/트레일링/정체보호 성공 로그는 result를 찍지 않으므로
    # ord_no를 그쪽 로그 문자열에 직접 넣어뒀다(2026-08-12) — 여기서 지우기 전에 확인할 것.
    return result


def buy_market(stk_cd: str, qty: int, dmst_stex_tp: str = 'KRX') -> dict:
    return place_order(stk_cd, qty, 0, side='1', trde_tp='3', dmst_stex_tp=dmst_stex_tp)


def sell_market(stk_cd: str, qty: int, dmst_stex_tp: str = 'KRX') -> dict:
    return place_order(stk_cd, qty, 0, side='2', trde_tp='3', dmst_stex_tp=dmst_stex_tp)


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


def get_unfilled_orders(acnt_no: str, acnt_pwd: str) -> List[Dict]:
    """미체결 주문(ka10075). 응답 리스트 키는 'oso'. 시장가만 쓰는 동안은 보통 빈 리스트다."""
    body = {
        'acnt_no': acnt_no, 'acnt_pwd': acnt_pwd,
        'all_stk_tp': '0', 'trde_tp': '0', 'stk_cd': '', 'stex_tp': '0',
    }
    data = _call('ka10075', '/api/dostk/acnt', body)
    return data.get('oso') or []
