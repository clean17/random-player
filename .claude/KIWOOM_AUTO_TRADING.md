# 키움 REST API 자동 매매 스크립트 설계

## 1. 전체 구조

```
job/
├── renew_kiwoom_token.py       # 기존: 토큰 발급 및 .env 저장
├── kiwoom_auto_trader.py       # 신규: 자동 매매 메인 스크립트
├── kiwoom_api.py               # 신규: API 호출 공통 모듈
└── kiwoom_strategy.py          # 신규: 매수/매도 전략 로직
```

---

## 2. 토큰 관리 전략

기존 `renew_kiwoom_token.py`의 `fn_au10001()`을 그대로 재사용.
토큰 유효기간은 키움 기준 **24시간**이므로 매일 장 시작 전(08:50) 갱신.

```python
# 토큰 자동 갱신 흐름
1. .env에서 MY_ACCESS_TOKEN 로드
2. API 호출 시 401 응답 → 즉시 재발급 후 재시도
3. 스케줄러로 매일 08:50 선제 갱신
```

---

## 3. 필요한 API 목록

| 용도 | api-id | endpoint | method |
|------|--------|----------|--------|
| 토큰 발급 | - | `/oauth2/token` | POST |
| 주식 현재가 | `ka10001` | `/api/dostk/mrkt` | POST |
| 매수/매도 주문 | `kt00001` | `/api/dostk/ordr` | POST |
| 주문 취소/정정 | `kt00002` | `/api/dostk/ordr` | POST |
| 계좌 잔고 조회 | `ka10007` | `/api/dostk/acnt` | POST |
| 미체결 주문 조회 | `ka10075` | `/api/dostk/ordr` | POST |
| 당일 체결 내역 | `ka10076` | `/api/dostk/ordr` | POST |
| 종목별 보유 수량 | `ka10085` | `/api/dostk/acnt` | POST |

> **참고:** api-id는 키움 REST API 문서 기준. 실제 문서에서 확인 후 수정 필요.

---

## 4. 공통 API 호출 모듈 (`kiwoom_api.py`)

```python
import requests
import json
import os
from dotenv import load_dotenv, find_dotenv
from job.renew_kiwoom_token import fn_au10001

dotenv_path = find_dotenv(usecwd=True) or ".env"
load_dotenv(dotenv_path=dotenv_path)

BASE_URL = 'https://api.kiwoom.com'
# BASE_URL = 'https://mockapi.kiwoom.com'  # 모의투자 테스트용

def _get_token():
    return os.environ.get('MY_ACCESS_TOKEN')

def _call_api(api_id: str, endpoint: str, data: dict,
              cont_yn: str = 'N', next_key: str = '') -> dict:
    """
    키움 REST API 공통 호출 함수.
    401 토큰 만료 시 자동 재발급 후 1회 재시도.
    """
    token = _get_token()
    headers = {
        'Content-Type': 'application/json;charset=UTF-8',
        'authorization': f'Bearer {token}',
        'cont-yn': cont_yn,
        'next-key': next_key,
        'api-id': api_id,
    }
    url = BASE_URL + endpoint
    response = requests.post(url, headers=headers, json=data)

    # 토큰 만료 시 재발급 후 재시도
    if response.status_code == 401:
        _refresh_token()
        headers['authorization'] = f'Bearer {_get_token()}'
        response = requests.post(url, headers=headers, json=data)

    response.raise_for_status()
    return response.json()

def _refresh_token():
    from dotenv import set_key
    params = {
        'grant_type': 'client_credentials',
        'appkey': os.environ.get('M_APP_KEY'),
        'secretkey': os.environ.get('M_SECRET_KEY'),
    }
    fn_au10001(data=params)
```

---

## 5. 주요 API 함수 구현

### 5-1. 현재가 조회
```python
def get_current_price(stk_cd: str) -> dict:
    """종목코드로 현재가 조회"""
    data = {'stk_cd': stk_cd}
    return _call_api('ka10001', '/api/dostk/mrkt', data)
    # 응답: {'stk_cd': '005930', 'cur_prc': '75000', 'flu_rt': '1.35', ...}
```

### 5-2. 계좌 잔고 조회
```python
def get_account_balance(acnt_no: str, acnt_pwd: str) -> dict:
    """계좌 잔고 및 보유 종목 조회"""
    data = {
        'acnt_no': acnt_no,   # 계좌번호 (8자리)
        'acnt_pwd': acnt_pwd, # 계좌비밀번호
        'qry_tp': '1',        # 1:합산, 2:개별
    }
    return _call_api('ka10007', '/api/dostk/acnt', data)
```

### 5-3. 매수/매도 주문
```python
def place_order(acnt_no: str, acnt_pwd: str,
                stk_cd: str, qty: int, price: int,
                order_type: str, trade_type: str) -> dict:
    """
    order_type: '1'=매수, '2'=매도
    trade_type: '00'=지정가, '03'=시장가, '05'=조건부지정가
    price: 시장가 주문 시 0 입력
    """
    data = {
        'acnt_no': acnt_no,
        'acnt_pwd': acnt_pwd,
        'stk_cd': stk_cd,
        'ordr_qty': str(qty),
        'ordr_prc': str(price),
        'buy_sell_tp': order_type,
        'ordr_tp': trade_type,
    }
    return _call_api('kt00001', '/api/dostk/ordr', data)
    # 응답: {'ordr_no': '0000123', 'stk_cd': '005930', ...}
```

### 5-4. 미체결 주문 취소
```python
def cancel_order(acnt_no: str, acnt_pwd: str,
                 orig_ordr_no: str, stk_cd: str, qty: int) -> dict:
    """미체결 주문 취소"""
    data = {
        'acnt_no': acnt_no,
        'acnt_pwd': acnt_pwd,
        'orig_ordr_no': orig_ordr_no,
        'stk_cd': stk_cd,
        'cncl_qty': str(qty),
        'ordr_tp': '00',
    }
    return _call_api('kt00002', '/api/dostk/ordr', data)
```

---

## 6. 전략 모듈 (`kiwoom_strategy.py`)

```python
class SimpleStrategy:
    """
    예시 전략: 이동평균 돌파 매수 / 손절-익절 매도
    실제 전략은 이 클래스를 상속하거나 교체
    """
    def __init__(self, buy_ratio: float = 0.3, stop_loss: float = -0.03,
                 take_profit: float = 0.05):
        self.buy_ratio = buy_ratio    # 가용 현금의 30% 매수
        self.stop_loss = stop_loss    # -3% 손절
        self.take_profit = take_profit  # +5% 익절

    def should_buy(self, stk_cd: str, current_price: int,
                   ma5: float, ma20: float) -> bool:
        """5일선이 20일선을 골든크로스하면 매수"""
        return ma5 > ma20

    def should_sell(self, stk_cd: str, current_price: int,
                    avg_price: int) -> bool:
        """손절 또는 익절 조건"""
        rate = (current_price - avg_price) / avg_price
        return rate <= self.stop_loss or rate >= self.take_profit

    def calc_buy_qty(self, available_cash: int, current_price: int) -> int:
        budget = int(available_cash * self.buy_ratio)
        return budget // current_price
```

---

## 7. 메인 자동 매매 스크립트 (`kiwoom_auto_trader.py`)

```python
import os
import time
import schedule
from dotenv import load_dotenv, find_dotenv
from job.kiwoom_api import get_current_price, get_account_balance, place_order
from job.kiwoom_strategy import SimpleStrategy

dotenv_path = find_dotenv(usecwd=True) or ".env"
load_dotenv(dotenv_path=dotenv_path)

ACNT_NO  = os.environ.get('KIWOOM_ACNT_NO')   # 계좌번호 .env에 추가
ACNT_PWD = os.environ.get('KIWOOM_ACNT_PWD')  # 계좌 비밀번호 .env에 추가

WATCH_LIST = ['005930', '000660', '035720']  # 감시 종목 리스트

strategy = SimpleStrategy()

def run_trading():
    """매 1분마다 실행되는 매매 로직"""
    balance = get_account_balance(ACNT_NO, ACNT_PWD)
    available_cash = int(balance.get('ord_psbl_amt', 0))

    for stk_cd in WATCH_LIST:
        price_info = get_current_price(stk_cd)
        cur_price  = int(price_info.get('cur_prc', 0))

        # TODO: 이동평균 계산 (별도 구현 필요)
        ma5, ma20 = calc_moving_average(stk_cd, 5), calc_moving_average(stk_cd, 20)

        # 매수 판단
        if strategy.should_buy(stk_cd, cur_price, ma5, ma20):
            qty = strategy.calc_buy_qty(available_cash, cur_price)
            if qty > 0:
                result = place_order(ACNT_NO, ACNT_PWD, stk_cd, qty, 0,
                                     order_type='1', trade_type='03')  # 시장가 매수
                print(f'[매수] {stk_cd} {qty}주 → {result}')

        # 매도 판단 (보유 종목에 한해)
        holding = get_holding(stk_cd, balance)
        if holding and strategy.should_sell(stk_cd, cur_price, holding['avg_prc']):
            result = place_order(ACNT_NO, ACNT_PWD, stk_cd, holding['qty'], 0,
                                  order_type='2', trade_type='03')  # 시장가 매도
            print(f'[매도] {stk_cd} {holding["qty"]}주 → {result}')

def is_market_open() -> bool:
    """장 운영 시간 체크 (09:00 ~ 15:30 평일)"""
    from datetime import datetime
    now = datetime.now()
    if now.weekday() >= 5:   # 토/일 제외
        return False
    t = now.time()
    from datetime import time as dtime
    return dtime(9, 0) <= t <= dtime(15, 30)

if __name__ == '__main__':
    print('자동 매매 시작')
    schedule.every(1).minutes.do(lambda: run_trading() if is_market_open() else None)

    while True:
        schedule.run_pending()
        time.sleep(10)
```

---

## 8. .env에 추가할 항목

```env
# 기존
M_APP_KEY=...
M_SECRET_KEY=...
MY_ACCESS_TOKEN=...

# 신규 추가
KIWOOM_ACNT_NO=12345678   # 계좌번호 (숫자만, 8자리)
KIWOOM_ACNT_PWD=****      # 계좌 비밀번호 (4자리)
```

---

## 9. 구현 순서 (권장)

1. **[1단계] 모의투자 환경 세팅**
   - `BASE_URL = 'https://mockapi.kiwoom.com'`으로 변경
   - 토큰 발급 → 계좌 잔고 조회 확인

2. **[2단계] 개별 API 검증**
   - 현재가 조회 → 주문 → 취소 순서로 단위 테스트

3. **[3단계] 전략 검증 (백테스트)**
   - 과거 데이터로 `SimpleStrategy.should_buy/sell()` 로직 검증

4. **[4단계] 실전 투자 소액 테스트**
   - `BASE_URL = 'https://api.kiwoom.com'`
   - 1주 단위로 시작

5. **[5단계] 스케줄러 연동**
   - `batch_runner.py`에 통합하거나 독립 프로세스로 실행

---

## 10. 주의사항

- **계좌 비밀번호는 절대 코드에 하드코딩 금지** → 반드시 `.env` 사용
- 키움 REST API는 **초당 요청 제한(Rate Limit)**이 있음 → 호출 간 `time.sleep(0.3)` 권장
- 장 시간 외 주문은 시간 외 단일가로 처리되므로 `is_market_open()` 체크 필수
- 연속조회(`cont-yn: Y`, `next-key`)가 필요한 API는 페이징 처리 구현 필요
- 실전 투자 전 반드시 **모의투자(`mockapi.kiwoom.com`)에서 충분히 테스트**
