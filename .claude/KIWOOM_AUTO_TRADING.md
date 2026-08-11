# 키움 자동매매 — API 레이어 & 운영 노트

최종 갱신 2026-08-12 · 코드 기준 `auto_trading/`

> **이 문서의 역할**: 키움 REST 레이어의 실사양과 이 코드를 건드릴 때 알아야 할 함정.
> **전략 파라미터(매수/매도 조건)는 여기 없다** → `auto_trading/TRADING_RULES.md` 참고.
>
> 2026-08-12 이전 버전은 **구현 전 설계 초안**이었고 실제 코드와 거의 모든 항목이 어긋나 있었다
> (api-id, 요청 body, 파일 구조, 전략, 실행 주기 전부). 아래는 코드에서 직접 확인한 값이다.

---

## 1. 파일 구조

```
auto_trading/
├── kiwoom_api.py               # REST 공통 호출 + 조회/주문 래퍼
├── renew_kiwoom_token.py       # 토큰 발급 (fn_au10001)
├── kiwoom_fire_strategy.py     # 신규 매수 (fire 신호)
├── kiwoom_trailing_stop.py     # 청산 + 거래이력/손익집계 + 수동매수/매도
├── request_kiwoom_thema.py     # 테마 조회 (스케줄 미등록)
├── kiwoom_fire_state.json      # 종목별 마지막 매수일, 당일 매수 건수  (gitignore)
├── kiwoom_trailing_state.json  # 종목별 고점·분할 진행상태            (gitignore)
├── TRADING_RULES.md            # 매수/매도 조건 스펙
└── backtest/
    ├── fire_backtest_regen.py      # 현재 규칙으로 백테스트 CSV 재생성
    └── fire_sizing_backtest.py     # 사이징 규칙 포트폴리오 재시뮬레이션
```

스케줄 등록은 `job/batch_runner.py`, 잡 래퍼는 `job/batch_process.py`.
로그·이력은 `logs/kiwoom_trading/` (`trading.log`, `trades.jsonl`, `asset_baseline.json`,
`market_breadth_cache.json`).

> ⚠️ 상태 파일 2개의 경로는 `os.path.dirname(__file__)` 기준이다. **코드를 다른 디렉터리로
> 옮기면 상태 파일도 반드시 같이 옮겨야 한다.** 잃으면 쿨다운이 초기화돼 2일 내 재매수가
> 발생하고, 트레일링 분할 진행상태가 리셋된다. 로그 경로는 루트 기준이라 영향 없다.

---

## 2. 환경 전환 (mock / real)

`.env`의 `KIWOOM_ENV`로 스위치한다(기본 `mock`). **모의·실전은 키와 계좌번호가 전부 다르다.**

| | mock | real |
|---|---|---|
| base_url | `https://mockapi.kiwoom.com` | `https://api.kiwoom.com` |
| app key | `KIWOOM_MOCK_APP_KEY` | `KIWOOM_APP_KEY` |
| secret | `KIWOOM_MOCK_SECRET_KEY` | `KIWOOM_SECRET_KEY` |
| token | `KIWOOM_MOCK_ACCESS_TOKEN` | `KIWOOM_ACCESS_TOKEN` |
| 계좌번호 | `KIWOOM_MOCK_ACNT_NO` | `KIWOOM_ACNT_NO` |
| 계좌비번 | `KIWOOM_MOCK_ACNT_PWD` | `KIWOOM_ACNT_PWD` |

계좌 정보는 **반드시 `get_account_credentials()`를 통해** 가져온다. 호출부에서 `.env` 키를 직접
읽으면 mock/real이 섞인다.

### 모의투자에서 안 되는 것

| 제약 | 응답 |
|---|---|
| **NXT 주문 전체** (프리 08:00~08:50, 애프터 15:30~20:00) | `RC9000: 모의투자에서는 해당업무가 제공되지 않습니다` (`return_code: 20`) |
| 장 종료 후 주문 | `RC4058: 모의투자 장종료` (`return_code: 20`) |

→ **mock에서는 실질적으로 09:00~15:20만 청산이 작동한다.** 프리마켓 갭 하락은 09:00까지 방치된다.
거부 메시지가 "모의투자에서는"이라고 명시하므로 실계좌에서는 NXT가 열릴 것으로 보이나
**검증된 바 없다.** 실계좌 전환 시 동작이 달라지며, 백테스트(일봉)는 이 차이를 반영하지 못한다.

---

## 3. 실제 API 목록

| 용도 | api-id | endpoint | 비고 |
|---|---|---|---|
| 토큰 발급 | — | `/oauth2/token` | `renew_kiwoom_token.fn_au10001()` |
| 현재가+종목명 | `ka10001` | `/api/dostk/stkinfo` | `mrkt`가 아니다 |
| 보유종목+계좌요약 | `kt00018` | `/api/dostk/acnt` | 실제로 쓰는 것은 이것 |
| 잔고 | `ka10007` | `/api/dostk/acnt` | `get_balance()` 정의만 있고 **미사용** |
| 매수 주문 | `kt10000` | `/api/dostk/ordr` | |
| 매도 주문 | `kt10001` | `/api/dostk/ordr` | 매수/매도를 **api-id로 구분**한다 |

### 미구현 (원 설계에는 있었으나 코드에 없음)

- **체결/미체결 조회** ← 가장 중요한 공백. 이것이 없어서 `order_accepted()`가 '주문 접수'까지만
  확인하고 **실제 체결 수량·가격은 확인하지 못한다.** 부분체결/미체결을 이력에서 걸러내려면 필요.
- 주문 취소/정정
- 연속조회(`cont-yn: Y` / `next-key`) 페이징 — `_call()`이 파라미터는 받지만 호출부에서 쓰지 않는다.

### 주문 요청 body

```python
{
  'dmst_stex_tp': 'KRX',   # 'KRX' | 'NXT' | 'SOR'
  'stk_cd': '005930',
  'ord_qty': '10',         # 문자열
  'ord_uv': '0',           # 지정가 단가, 시장가는 '0'
  'trde_tp': '3',          # '3' 시장가 / '0' 보통(지정가)
}
```

**계좌번호·비밀번호는 주문 body에 넣지 않는다** (토큰으로 식별). 조회 API(`kt00018` 등)에만 넣는다.

### 응답 판정

```python
성공  {'ord_no': '0157630', 'dmst_stex_tp': 'KRX', 'return_code': 0, 'return_msg': '모의투자 매수주문완료'}
거부  {'return_msg': '[2000](RC9000:...)', 'return_code': 20}      # ord_no 없음
```

`order_accepted(result)` (`kiwoom_trailing_stop.py`) — `return_code == 0` **AND** `ord_no` 존재.
**주문을 내는 모든 지점에서 이 게이트를 통과시켜야 한다.** 거부 시 이력 미기록 + 포지션 상태
미변경 + fire는 슬롯/한도 미소진. 자세한 내용은 TRADING_RULES.md 4절.

---

## 4. `_call()`의 함정 세 가지

`kiwoom_api.py:88`

1. **토큰 만료가 HTTP 401로 안 올 수 있다.** 키움은 `200 + return_code≠0 + '인증'` 포함 메시지로
   내려줄 때가 있다. 그대로 두면 숫자 필드가 **조용히 전부 0으로 파싱된다**(잔고 0, 현재가 0).
   `_is_invalid_token_response()`가 이걸 잡아 토큰 재발급 후 1회 재시도한다.
2. **Rate limit은 호출별 sleep으로 부족하다.** 30초 트레일링 잡·5분 계좌현황 잡·대시보드 요청이
   서로 다른 스레드에서 동시에 때린다. `threading.Lock` + 전역 `_last_call_ts`로 프로세스 전체에서
   호출 간격 **0.35초**를 보장한다.
3. **429는 별도로 백오프 재시도**한다(0.5s → 1.0s → 1.5s, 최대 3회). 실매매 로그에 자주 찍힌다 —
   2026-08-11 15:18 매수 사이클(18후보/11매수, 16초)에 429 재시도가 6회 있었다.

토큰 갱신 스케줄은 **매일 07:00** (`batch_runner.py`, `schedule` + `CronTrigger` 양쪽에 등록).

---

## 5. 변경 반영 방법 — 재시작이 필요한 경우

`run.py`(스케줄러)가 상시 가동 중이다. **모듈이 `sys.modules`에 캐시되므로 파일만 고쳐도
반영되지 않을 수 있다.**

| 변경 대상 | 재시작 필요? |
|---|---|
| `kiwoom_trailing_stop.py` | **필요.** 30초 잡이 이미 로드해 캐시하고 있다 |
| `kiwoom_api.py` | **필요.** 위 모듈이 import 시점에 끌어온다 |
| `kiwoom_fire_strategy.py` | **조건부.** `batch_process.py:257`이 함수 내부에서 import하므로, 그날 15:18 잡이 아직 안 돌았고 프로세스가 그 이후 시작됐다면 다음 15:18에 새 코드를 읽는다 |
| 파일 이동·이름 변경 | **반드시 필요.** 캐시된 `batch_process`가 구 경로를 참조해 `ImportError`가 나고, 매수가 조용히 스킵된다 |
| `batch_runner.py` / `batch_process.py` | **필요** |

확인 방법: `logs/kiwoom_trading/trading.log`에서 프로세스 시작 이후 해당 잡의 로그가 찍혔는지 본다.
찍혀 있으면 이미 캐시된 상태다.

재시작은 **장 시작(08:00 NXT 프리마켓) 전**에 하는 것이 안전하다.

---

## 6. 작업 시 주의사항

- **라이브 계좌가 돌고 있다.** 파라미터를 바꾸면 다음 거래일에 실제 주문에 반영된다.
  근거 없는 값 변경은 하지 않는다. 각 상수의 채택 근거는 해당 파일 docstring에 백테스트 수치로 남아 있다.
- **계좌 비밀번호를 코드에 넣지 않는다.** 반드시 `.env`.
- **하드코딩된 절대경로가 있다.** `batch_process.py`가 서브프로세스를 절대경로로 띄운다
  (`C:\my-project\random-player\auto_trading\renew_kiwoom_token.py` 등). 파일을 옮기면 함께 고쳐야 한다.
  ⚠️ Windows 경로를 스크립트로 일괄 치환하면 `\a`(BEL) `\b` `\t` 등이 이스케이프로 해석돼
  **매칭은 되는데 치환 결과만 깨진다.** 경로 문자열은 Edit으로 직접 고치고, 고친 뒤
  `os.path.exists()`로 검증할 것.
- **백테스트 절대 수익률을 믿지 않는다.** 상세는 TRADING_RULES.md 8절. 요약:
  reserved 교집합 재현 불가(전 종목 체크 가정), 일봉이라 30초 잡의 일중 경로 재현 불가,
  NXT 시간대 미반영. 규칙 간 **상대 비교**에만 쓴다.
- **`trades.jsonl`의 절대 손익은 어긋나 있다.** 자동청산 74건 실현손익 −3,212,045원인데
  `asset_baseline.json` 월간 손익은 −76,547원이다. 비율(건당 수익률) 비교에는 쓸 수 있으나
  절대 손익은 원인 규명 전까지 인용하지 말 것. (미해결)
- **`sell_market`/`buy_market`을 스텁으로 대체하는 검증 스크립트**는 성공 형태
  (`{'return_code': 0, 'ord_no': ...}`)를 반환해야 한다. 아니면 `order_accepted()`에 걸려
  매도가 전부 건너뛰어진다.

---

## 7. CLI

```bash
# 매수 없이 오늘 후보/레짐만 확인
python -m auto_trading.kiwoom_fire_strategy --check [--force]

# 수동 매수/매도
python -m auto_trading.kiwoom_trailing_stop --buy <종목코드> [수량]
python -m auto_trading.kiwoom_trailing_stop --sell <종목코드> <수량>

# 백테스트 (psycopg 필요 → venv 파이썬)
venv/Scripts/python.exe auto_trading/backtest/fire_backtest_regen.py [--no-same-day-trigger]
python auto_trading/backtest/fire_sizing_backtest.py <csv> all
```

---

## 8. 미해결 과제

1. **체결조회 API 연동** — `order_accepted()`가 '접수'까지만 확인한다. 부분체결/미체결이
   이력에 성공으로 남는다.
2. **`trades.jsonl` 손익 불일치** (6절 참고).
3. **전략 기대값이 0 근처다.** 현재 청산규칙으로 재생성한 백테스트에서 건당
   −0.740% ~ +0.161%(일중 근사 비관/낙관 극단), 실제 체결 −0.059%. 왕복비용 0.2%를 얹으면
   확실히 마이너스. 손절 −6%에 53%가 걸린다. **사이징보다 손절·트레일링 파라미터와 진입 조건
   (2026-08-05 H2 필터 제거로 후보가 13 → 54종목/일)이 우선 검토 대상.**
4. **NXT 시간대 동작을 mock으로 검증할 수 없다.** 실계좌에서 처음 겪는다.
5. `interest_v2` 신호는 2026-08-11 도입으로 데이터가 1일뿐이라 백테스트 불가.
