# 프로젝트 환경

## Python 버전: 3.8.10

Python 코드 작성 시 아래 규칙을 반드시 준수한다.

### 사용 금지 (3.9+ 문법)
- `list[str]`, `dict[str, int]`, `tuple[str, ...]` → `List`, `Dict`, `Tuple` from `typing` 사용
- `str.removeprefix()`, `str.removesuffix()` → 직접 슬라이싱으로 대체

### 사용 금지 (3.10+ 문법)
- `match` 문 → `if/elif` 사용
- `X | Y` 타입 유니온 → `Union[X, Y]` from `typing` 사용
- `int | None` → `Optional[int]` from `typing` 사용

### 타입 힌트 작성 규칙
```python
# ❌ 3.9+
def foo(x: list[str]) -> dict[str, int]: ...

# ✅ 3.8
from typing import List, Dict, Optional, Union, Tuple
def foo(x: List[str]) -> Dict[str, int]: ...
```

## 실행: 반드시 venv 파이썬

```bash
venv/Scripts/python.exe <script>       # ✅
python <script>                        # ❌ 대개 ImportError
```

`python`은 WindowsApps 3.8.10로 잡히는데 **`psycopg`·`apscheduler`·`dotenv`·`requests`·
`concurrent_log_handler`가 없다**(`pandas`/`numpy`/`flask`만 있음). DB·키움 API·스케줄러를 건드리는
코드는 전부 venv로 돌려야 한다. 순수 계산/분석 스크립트만 예외적으로 `python`으로도 돈다.

## 콘솔 출력 인코딩

Windows 콘솔이 cp949라서 한글이 깨지고, `—`(em dash) 같은 문자는 `UnicodeEncodeError`로 죽는다.

```bash
PYTHONIOENCODING=utf-8 venv/Scripts/python.exe <script>
```
```python
try:
    sys.stdout.reconfigure(encoding='utf-8')   # 스크립트 안에서도 같이 걸어둘 것
except Exception:
    pass
```

## Windows 경로를 스크립트로 일괄 치환하지 말 것

`\a`(BEL) `\b` `\t` `\v` `\f`가 이스케이프로 해석돼 **매칭은 되는데 치환 결과만 깨진다.**
실제 사고: `\job\` → `\auto_trading\` 치환이 `C:\my-project\random-player` + BEL + `uto_trading\`로
저장돼 서브프로세스 경로가 조용히 망가졌다(문자열 검색으로는 안 잡히고 파일이 존재하는지 확인해야
발견된다).

- 경로 문자열은 **Edit 도구로 직접** 고친다.
- 고친 뒤 `os.path.exists()`로 검증한다.
- 제어문자 혼입 점검: 소스에 `\x00 \x07 \x08 \x0b \x0c \x1b`가 있으면 손상이다.

## ⚠️ 실계좌 자동매매가 상시 가동 중 (`.env` KIWOOM_ENV=real)

`run.py` 스케줄러가 돌고 있고 실제로 주문을 낸다. **2026-08-19 v8 전환:**

| | 매수 | 청산 |
|---|---|---|
| v8 (가동) | 15:55 스크리닝 + 장중 60초 지정가 대기 | 30초 (ATR 샹들리에/트레일링/익절/10일) |
| fire (실전 중단 / **모의는 15:21 동시호가 시장가로 가동 중**) | ~~시장가 매수~~ 주석 처리(실전) | 30초 (손절-6%/보유 실전15일·모의5일) — v8 미소유 종목만 |

청산 2개가 동시에 도는데 **담당 종목이 소유권으로 갈린다**(`v8_owned_codes()`).

- **파라미터를 근거 없이 바꾸지 않는다.** 각 상수의 채택 근거가 해당 파일 docstring에 백테스트
  수치로 남아 있다. 바꿀 때는 `auto_trading/backtest/`로 재검증하고 근거를 같이 기록한다.
- **파일을 고쳐도 반영되지 않을 수 있다.** 모듈이 `sys.modules`에 캐시된다. 무엇을 고치면
  재시작이 필요한지는 `.claude/KIWOOM_AUTO_TRADING.md` 5절 표를 볼 것.
  파일 이동·이름 변경은 **반드시** 재시작해야 하고, 안 하면 매수가 조용히 스킵된다.
- **상수를 바꾸면 `log_config()`도 같이 갱신한다.** `kiwoom_v8_strategy.log_config()` /
  `kiwoom_v8_exit.log_config()` / `kiwoom_trailing_stop.log_config()` /
  `kiwoom_fire_strategy_mock.log_config()`가 서버 시작 시 각 모듈의 실제 상수값을 로그 맨
  앞에 찍는다(2026-09-15 도입 — "재시작했으니 새 값 반영됐겠지"를 눈으로 확인할 방법이
  없었던 게 반복된 사고 원인이었다). 상수를 추가·변경했으면 해당 모듈의 `log_config()`도
  같이 고쳐야 한다 — 안 그러면 로그가 낡은 값을 계속 보여줘서 오히려 오판의 원인이 된다.
  재시작 후엔 반드시 이 로그 줄로 새 값이 실제로 들어갔는지 확인할 것.
- 상태 파일(`auto_trading/kiwoom_*_state.json`)은 `dirname(__file__)` 기준이다. 코드를 옮기면
  같이 옮겨야 한다 — 잃으면 쿨다운과 트레일링 진행상태가 초기화된다.

## IDE `no-commit` 변경 목록은 커밋·푸시 금지

JetBrains IDE의 `no-commit` changelist에 들어 있는 파일은 **커밋도 푸시도 하지 않는다.**
git은 changelist를 모르기 때문에 `git status`에는 일반 수정 파일로 보인다 — 커밋 전에 매번 확인할 것.

```bash
# no-commit 목록의 파일 확인 (.idea/workspace.xml 은 gitignore 대상, 로컬에만 있음)
grep -A50 'name="no-commit"' .idea/workspace.xml | sed '/<\/list>/q' | grep -o 'afterPath="[^"]*"'
```

- 커밋할 파일만 경로를 지정해서 `git add`한다. `git add -A` / `git add .` / `git commit -a` 금지.
- 같은 파일에 커밋할 변경과 no-commit 변경이 섞여 있으면 임의로 판단하지 말고 사용자에게 물어본다.

## logs/ 는 gitignore 대상

백테스트 결과 CSV처럼 추적해야 하는 산출물은 `git add -f`가 필요하다(갱신할 때도 매번).

## 문서 위치

| 문서 | 내용 |
|---|---|
| `auto_trading/TRADING_RULES.md` | 매수/매도 조건 스펙, 파라미터, 알려진 한계 (0절 = v8) |
| `auto_trading/V8_SWITCHOVER.md` | v8 전환 상태, 백테스트와 실매매 차이, 되돌리기 |
| `.claude/KIWOOM_AUTO_TRADING.md` | 키움 API 실사양, `_call()` 함정, 재시작 규칙, 미해결 과제 |

자동매매 코드를 건드리기 전에 두 문서를 먼저 읽는다. 값을 바꾸면 문서도 같이 고친다.
