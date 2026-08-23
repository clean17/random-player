# 키움 자동매매 — API 레이어 & 운영 노트

최종 갱신 2026-08-19 · 코드 기준 `auto_trading/`

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
├── kiwoom_fire_strategy.py     # fire 매수 — 2026-08-19 스케줄 중단(코드는 유지)
├── kiwoom_trailing_stop.py     # 청산 + 거래이력/손익집계 + 수동매수/매도
│                               #   v8 소유 종목은 건너뛴다 (v8_owned_codes)
├── kiwoom_v8_strategy.py       # v8 매수 — 매일 스크리닝 + 지정가 대기  (2026-08-19~)
├── kiwoom_v8_exit.py           # v8 청산 — ATR 샹들리에/트레일링/익절/보유상한
├── v8_limit_order_test.py      # 지정가 주문 1주 검증용 CLI
├── request_kiwoom_thema.py     # 테마 조회 (스케줄 미등록)
├── kiwoom_fire_state.json      # 종목별 마지막 매수일, 당일 매수 건수  (gitignore)
├── kiwoom_trailing_state.json  # 종목별 고점·분할 진행상태            (gitignore)
├── kiwoom_v8_pending_real.json # v8 대기 후보 + 소유권 원장 + 아침 캐시 (gitignore)
├── kiwoom_v8_positions_real.json # v8 포지션 peak/분할 진행상태        (gitignore)
├── TRADING_RULES.md            # 매수/매도 조건 스펙 (0절 = v8)
├── V8_SWITCHOVER.md            # v8 전환 절차·차이·리스크
└── backtest/
    ├── fire_backtest_regen.py      # 현재 규칙으로 백테스트 CSV 재생성
    └── fire_sizing_backtest.py     # 사이징 규칙 포트폴리오 재시뮬레이션
```

스케줄 등록은 `job/batch_runner.py`, 잡 래퍼는 `job/batch_process.py`.
로그·이력은 `logs/kiwoom_trading/` (`trading.log`, `trades.jsonl`, `asset_baseline.json`,
`market_breadth_cache.json`).

> ⚠️ 상태 파일 4개의 경로는 `os.path.dirname(__file__)` 기준이다. **코드를 다른 디렉터리로
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
| 당일 체결내역 | `ka10076` | `/api/dostk/acnt` | `get_filled_orders()`. `ordr`이 아니라 **`acnt`** |
| 미체결 주문 | `ka10075` | `/api/dostk/acnt` | `get_unfilled_orders()`. 리스트 키는 `oso` |
| 매수 취소 | `kt10003` | `/api/dostk/ordr` | `cancel_order(side='1')` (2026-08-19 추가) |
| 매도 취소 | `kt10004` | `/api/dostk/ordr` | `cancel_order(side='2')` |

`ka10076` 응답(2026-08-12 모의투자 실응답으로 검증): `{'cntr': [ {...} ]}`.
항목 필드는 전부 문자열 — `ord_no` / `stk_cd` / `io_tp_nm`('+매수'/'-매도') / `ord_qty` /
**`cntr_qty`(체결수량)** / **`cntr_pric`(체결단가)** / **`oso_qty`(미체결수량)** /
`tdy_trde_cmsn`(수수료) / `tdy_trde_tax`(거래세, 매수는 0) / `ord_stt` / `ord_tm`(HHMMSS).

> ⚠️ `ka10076`에는 **날짜 파라미터가 없다** → '당일분'만 준다. 소급 정산은 같은 날에만 가능하다.
> `kt00007`(계좌별주문체결내역상세)에 `ord_dt`가 있으나 모의투자에서 '해당조회내역이 없습니다'로
> 비어서 쓰지 않는다.

### 미구현

- 주문 **정정**(수량/가격 변경) — v8은 '취소 후 재주문'으로 처리한다. 호가 대기순번을 잃으므로
  `RESIZE_TOL`(20%) / `REGAP_MARGIN`(3%p) 문턱을 두고 함부로 바꾸지 않는다.
- 연속조회(`cont-yn: Y` / `next-key`) 페이징 — `_call()`이 파라미터는 받지만 호출부에서 쓰지 않는다.

> **주문 취소는 2026-08-19 구현됐다** (`cancel_order`). v8이 지정가 미체결을 다루기 때문에 필요해졌다.
> 실계좌에서 접수/취소 왕복 확인됨(주문번호 0274100).
> ⚠️ 지정가 매수는 **하한가보다 낮으면 거부**된다: `[2000](571552:주문단가가 하한가보다 낮습니다.)`.
> 하한가 = 전일 종가 × 0.70 (호가단위 올림). **전일 종가는 pkl 마지막 행이 아니다** —
> 장중 pkl 마지막 행은 오늘 진행중 데이터다(2026-08-19 005930: pkl 251,000 vs 실제 전일 268,500).
> `kiwoom_v8_strategy.prev_close_of()` 처럼 `index < today` 로 잘라내야 한다.

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

### 체결 정산 (`reconcile_fills()`)

주문 시점에 기록되는 `price`/`qty`는 **조회가와 주문수량**이다. 실제 체결값은 사후 정산으로 채운다.

- 평일 **20:10** 스케줄(`kiwoom_reconcile_fills`, NXT 애프터마켓 20:00 종료 후). 조회 전용이라
  `is_market_open()` 체크를 하지 않는다.
- `ord_no` 매칭이 1순위. 없으면 (종목+구분+체결수량+시각 120초 내) 폴백 —
  **수량만으로는 안 된다**(2026-08-11 코칩 매도 2건이 둘 다 9주였고, 수량만 보면 어긋난다).
  그래서 `_record_trade()`가 `ord_no`를 반드시 기록한다.
- 채우는 필드: `fill_qty` `fill_price` `unfilled` `cmsn` `tax` `slippage` `fill_pnl` `fill_src`
- 원자적 파일 교체(`.tmp` → `os.replace`), 이미 정산된 건은 건너뛰어 여러 번 돌려도 안전.
- 주문 직후가 아니라 사후에 하는 이유: ① 체결 지연으로 직후 조회는 미체결로 보일 수 있다
  ② fire 매수는 15:18~15:20 2분 안에 최대 20건인데 건당 호출 간격(당시 0.35초, 현재 0.143초)
     조회를 끼우면 마감을 넘길 수 있다
  ③ 정산이 실패해도 주문 시점 기록은 남는다.

---

## 4. `_call()`의 함정 세 가지

`kiwoom_api.py:88`

1. **토큰 만료가 HTTP 401로 안 올 수 있다.** 키움은 `200 + return_code≠0 + '인증'` 포함 메시지로
   내려줄 때가 있다. 그대로 두면 숫자 필드가 **조용히 전부 0으로 파싱된다**(잔고 0, 현재가 0).
   `_is_invalid_token_response()`가 이걸 잡아 토큰 재발급 후 1회 재시도한다.
2. **Rate limit은 호출별 sleep으로 부족하다.** 30초 트레일링 잡·5분 계좌현황 잡·대시보드 요청이
   서로 다른 스레드에서 동시에 때린다. `threading.Lock` + 전역 `_last_call_ts`로 프로세스 전체에서
   호출 간격을 보장한다.

   **간격 값 (2026-08-19 `ka10001` 실측으로 0.35초 → 0.143초 변경)**

   | 설정 | 목표 건/초 | 429 발생 | 실효 건/초 |
   |---:|---:|---:|---:|
   | 0.0556 | 18.0 | 2건 | 6.0 |
   | 0.1000 | 10.0 | 1건 | 6.8 |
   | **0.1429** | **7.0** | **0건** | **6.3** |
   | 0.2000 | 5.0 | 0건 | 4.9 |

   문서에는 계좌·토큰당 20건/초라고 되어 있지만 **10건/초에서도 429가 났다.** 그리고 429 백오프
   재시도 비용 때문에 **실효 처리량이 어느 설정에서든 6~7건/초로 수렴**한다 — 18건/초로 설정하면
   실효 6.0건/초로 7건/초 설정보다 오히려 낮다. 더 밀어붙이는 게 순손실이다.
   그래서 429가 나지 않는 최대치인 **7건/초(0.143초)**를 쓴다.
   이전 값 0.35초(2.86건/초)는 근거 주석 없이 보수적으로 잡혀 있었다.

   ⚠️ 프로세스 전역 값이다. 한 계좌에 여러 프로세스를 붙이면 합산이 한도를 넘으므로 더 낮춰야 한다.
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
| `kiwoom_fire_strategy.py` | **조건부.** `batch_process.py:257`이 함수 내부에서 import하므로, 그날 15:18 잡이 아직 안 돌았고 프로세스가 그 이후 시작됐다면 다음 15:18에 새 코드를 읽는다 (⚠️ 2026-08-19 이후 이 잡은 주석 처리돼 돌지 않는다) |
| `kiwoom_v8_strategy.py` | **필요.** 60초 매수 잡이 캐시하고 있다 |
| `kiwoom_v8_exit.py` | **필요.** 30초 청산 잡이 캐시하고 있다 |
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
- **`trades.jsonl` 손익을 `asset_baseline.json`과 비교할 때 기간을 반드시 맞춘다.**
  `asset_baseline.json`의 `monthly_start`는 **당월** 스냅샷인데 `trades.jsonl`은 전 기간이다.
  2026-08-12에 "자동청산 74건 −3,212,045원 vs 월간 −76,547원"으로 비교해 불일치라고 오판한 적이
  있는데, 월별로 쪼개면 맞는다:
  ```
  2026-07 매도 실현손익  −2,943,743원   ← 8월 월간 지표에 안 들어감
  2026-08 매도 실현손익     −67,512원
  2026-08 자산변화          −76,547원   → 차이 9,035원 (미실현 변동 + 수수료·세금 범위)
  ```
- **`pnl` 필드는 수수료·세금을 반영하지 않는다.** 정산 후의 `cmsn`/`tax`를 따로 빼야 실질 손익이
  된다. 2026-08-11 실측: 매도 pnl 합 +17,921원인데 수수료+세금이 17,182원으로 **실질 +739원**이었다.
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

# 당일 체결내역 확인 / 거래이력 정산 (정산은 같은 날에만 가능)
python -m auto_trading.kiwoom_trailing_stop --fills
python -m auto_trading.kiwoom_trailing_stop --reconcile [--dry-run] [--date YYYY-MM-DD]

# 응답 원본 필드 확인 (보유종목)
python -m auto_trading.kiwoom_trailing_stop --dump

# 백테스트 (psycopg 필요 → venv 파이썬)
venv/Scripts/python.exe auto_trading/backtest/fire_backtest_regen.py [--no-same-day-trigger]
python auto_trading/backtest/fire_sizing_backtest.py <csv> all
```

---

## 8. 실측으로 확인된 것 (2026-08-11 21건, 소급 정산)

**슬리피지는 무시할 수준이다.** 매수 **+0.034%**(유리), 매도 **−0.024%**(불리). 21건 중 12건은
체결가가 주문 시점 조회가와 정확히 일치했고, 최대 이탈도 −0.535% / +0.634%였다.
→ **백테스트가 '조회가에 체결된다'고 가정한 것은 타당하다.** 슬리피지가 기대값의 부호를
바꿀 것이라는 우려는 기각됐다.

**미체결은 0건이었다.** 전량 시장가 주문이 정규장에서 모두 전량 체결됐다.
→ `order_accepted()`의 '접수 = 체결' 가정이 이 표본에서는 성립했다. 다만 보장은 아니므로
정산이 `unfilled`를 계속 감시한다(부분체결 감지 시 ERROR 로그).

**거래비용이 크다 — 그리고 mock과 실계좌가 다르다.**

| | 편도 | 내역 |
|---|---|---|
| 매수 | **0.345%** | 수수료만 |
| 매도 | **0.546%** | 수수료 ~0.35% + 거래세 0.18% |
| **왕복** | **0.881%** | |

이건 **모의투자 수수료율**이다. 실계좌 키움 온라인 수수료는 훨씬 낮고(0.015% 수준) 거래세
0.18%는 동일하게 붙어, 실계좌 왕복은 대략 **0.21%**로 추정된다.
→ **모의투자 성과는 실계좌보다 구조적으로 나쁘다.** mock 실적으로 전략을 평가할 때 반드시 감안.
백테스트의 왕복 0.2% 민감도 가정은 실계좌 기준으로는 타당하다.

---

## 9. 미해결 과제

1. **전략 기대값이 0 근처다.** 현재 청산규칙으로 재생성한 백테스트에서 건당
   −0.740% ~ +0.161%(일중 근사 비관/낙관 극단), 실제 체결 −0.059%. 손절 −6%에 53%가 걸린다.
   **사이징보다 손절·트레일링 파라미터와 진입 조건(2026-08-05 H2 필터 제거로 후보가
   13 → 54종목/일)이 우선 검토 대상.**
   참고: 8월 자동청산은 −73,232원(39건)으로 7월(−3,138,813원, 40건)보다 규모·손실이 크게
   줄었다. 7월은 파라미터를 계속 바꾸며 테스트한 기간이고 티엘비 액면분할 오인 청산
   −939,000원도 포함된다. 8월 데이터가 쌓이면 재조정 효과를 실측으로 볼 수 있다.
2. **NXT 시간대 동작을 mock으로 검증할 수 없다.** 실계좌에서 처음 겪는다.
3. `interest_v2` 신호는 2026-08-11 도입으로 데이터가 1일뿐이라 백테스트 불가.

### 해결됨

- ~~체결조회 API 연동~~ → 2026-08-12 `ka10076` 연동 + `reconcile_fills()` 구현 (3·4절)
- ~~`trades.jsonl` 손익 불일치~~ → 불일치가 아니었다. 기간을 잘못 맞춰 비교한 것 (6절)
- ~~슬리피지가 기대값을 뒤집을 수 있다~~ → 실측 ±0.03% 수준으로 무영향 (8절)
