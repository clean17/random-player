"""
키움 계좌 보유 종목 자동 청산.

━━━ 현재 운영 규칙 (2026-08-14~) ━━━
  실전(KIWOOM_ENV=real): 손절 -6% + 보유 5영업일 상한. 트레일링 OFF.
  모의(KIWOOM_ENV=mock): 손절 -6% + 트레일링 ON + 보유 15영업일 상한 (2026-08-14 이전 '예전 방식').
  환경별 분기는 TRAILING_ENABLED / MAX_HOLD_DAYS 정의부 주석 참고 (2026-08-20).

  3년치(2023-04~2026-08, 신호 30,205건) 연도별 검증에서 트레일링이 4개 연도 '전부' 손실을
  냈다(현행 상회 0/4). 같은 신호에 청산만 바꾼 연도별 평균 %(왕복비용 0.2% 반영 전):
                              2023    2024    2025    2026    전체   비용후
    트레일링(최대15일)         -1.009  -1.290  -0.455  -0.384  -0.794  -0.994
    트레일링 튜닝(활성3/gap3)  -0.627  -0.724  -0.378  -0.362  -0.526  -0.726
    손절-6% + 5일 보유         -0.120  -0.075  +0.578  +0.705  +0.267  +0.067  ← 채택
  이 신호의 수익은 1~3일에 몰려 있는데(1일 +0.106% / 3일 +0.085% / 10일 -0.918% / 20일 -1.366%)
  트레일링은 +7%까지 올라야 켜지고 5%p 되돌릴 때까지 안 팔아, 수익 구간이 끝난 뒤에 나온다.
  ⚠️ 비용 후 +0.067%는 '간신히 본전 위'다. 2023·2024년은 개선 후에도 마이너스이고, pkl에
     상장폐지 종목이 빠져 있어(생존편향) 실제는 이보다 낮다.
  검증 스크립트: auto_trading/backtest/exit_validation_3y.py

━━━ 아래는 TRAILING_ENABLED=True로 되돌렸을 때의 규칙 (현재 비활성) ━━━
기본 전략 (수정하려면 아래 상수만 변경):
  - 손절            : -6%  → 전량 즉시 청산
  - 되돌림 손절     : 한 번이라도 +5%를 찍었던(트레일링 활성화된) 종목도 손절선은 동일하게 -6%
    → 전량 즉시 청산. 이익 구간까지 갔던 종목을 더 내주지 않기 위함(ARMED_GIVEBACK_STOP).
    ※ 현재 두 값이 같아 실질적인 동작 차이는 없다. 되돌림만 더 좁게 가져가려면
      ARMED_GIVEBACK_STOP만 STOP_LOSS_RATE보다 작은 폭으로 바꾸면 된다.
  - 목표가          : 비활성화(TARGET_RATES=[]). 익절은 전적으로 트레일링이 담당.
    고정 사다리(10/15/20%)는 상승 종목을 일찍 끊어 성과를 깎는 것으로 검증돼 껐다.
  - 트레일링 활성화 : 수익률 +7% 도달 후 고점 추적 시작
  - 트레일링 폭     : 고점 대비 -5%p 이탈 시 그 시점 잔여 수량의 1/3 매도
  - 최소 익절 보호선 : +3% (트레일링 청산선이 +3% 밑으로 내려가지 않도록 고정).
    활성화(+7%) - 폭(5%p) = +2% < 보호선(+3%)이라, 고점이 7~8% 구간이면 청산선이 항상
    보호선(3%)에 붙는다 — 고점이 8%를 넘어야 트리거선이 보호선 위로 올라가 정상적인
    고점-5%p 트레일링이 된다.
    ※ 보호선에 걸린 경우는 다른 트리거(1/3만 매도)와 달리 잔여 전량을 정리한다 — "발동선을
    갓 넘겼다가 바로 꺾이는 약한 모멘텀"이라 남겨봤자 대개 정체보호/되돌림손절로 이어진다는
    재검증 결과(1년 재현 데이터 87건 기준, 기하평균 +0.199%→+0.220%로 개선). 예전엔 반대로
    "1/3만 매도"로 바꾼 적이 있는데, 그때는 활성화 5%/보호선 1%라 거의 모든 트레일링이
    보호선에 걸리는 구조였다(지엔씨에너지 사례). 지금은 활성화·보호선을 같이 올려서 보호선이
    선택적으로만 걸리므로 전량청산이 유리하다.
  - 한 종목당 최대 3회(3분할)까지만 매도 — 목표가를 껐으므로 사실상 트레일링이 3분할을 다 쓴다
    (단, 보호선 트리거는 예외적으로 1회에 전량 정리).
    트레일링 매도는 "직전 매도 시점의 고점보다 더 높은 새 고점"을 갱신해야만 다시 트리거됨
    (같은 고점에서 반복 매도되는 것 방지).
  - 보유 중 추가 매수로 평단가가 바뀌면 고점/목표가 단계 등 진행상태는 리셋되고 새 평단가 기준으로
    사다리/트레일링을 처음부터 다시 평가함 (rate가 평단가 기준 값이라 예전 %는 더 이상 같은 척도가 아님).
  - 정체 보호: 트레일링 매도(갭 트리거)가 한 번 나간 뒤 그보다 더 높은 새 고점 없이 가격이
    계속 흘러내리면 트레일링이 재발동되지 않아 잔여 물량이 보호 없이 노출될 수 있음. 이를
    막기 위해 그 매도에 쓰인 트리거선(고점-5%p)보다 추가로 -6%p(STALL_GAP) 더 밀리면 잔여
    전량 청산. 고점이 높았던 종목(예: 고점 20% → 트리거 15% → 9%에서 정리)에 주로 작동한다.
    ※ 보호선 트리거는 애초에 1회에 전량 정리되므로(위 참고) 정체 보호가 뒤이어 평가될 잔여
    물량 자체가 없다 — 정체 보호는 사실상 갭 트리거로 시작한 포지션에만 해당한다.
  - 기업행위 방어: 액면분할·권리락 당일엔 증권사가 현재가만 먼저 조정하고 평단가/수량은 늦게
    조정하는 구간이 있어 손실률이 -50%대로 잘못 잡힐 수 있음. 일일 가격제한폭(±30%)을 넘는 급락이나
    정상적으로 도달 불가능한 손실률이 관측되면 매도하지 않고 경고만 남긴 뒤 자동매매를 일시 정지함
    (ANOMALY_DROP / ANOMALY_RATE). 값이 정상 범위로 돌아오면 자동 재개.

30초 간격으로 호출되는 것을 전제로 설계됨 (job/batch_runner.py에 등록).
실제 평가/매매는 is_market_open() 기준 월~금 **09:00~15:20(KRX 정규장)** 에서만 수행됨.
08:50~09:00(동시호가)과 15:20~15:30(KRX 종가 단일가매매)은 연속체결이 아니라서 제외한다.

NXT(넥스트트레이드) 프리 08:00~08:50 / 애프터 15:30~20:00은 2026-08-18에 제외했다 —
시장가 주문을 받지 않아 실계좌에서도 전량 거부됐다(407022). 상세는 is_market_open() 위 주석.
따라서 프리마켓 갭 하락은 09:00까지 방치된다. 실전 투자 전 KIWOOM_ENV=mock으로 먼저 검증할 것.
"""
import os
import json
import logging
import logging.handlers
import datetime
from typing import Dict, Optional
from dotenv import load_dotenv, find_dotenv

from auto_trading.kiwoom_api import get_holdings_and_summary, sell_market, buy_market, get_current_price, get_current_price_and_name, \
    dump_holdings_raw, get_account_credentials, get_account_summary, get_filled_orders, env_path, \
    cancel_order, KIWOOM_ENV, VALID_ENVS
from typing import List

dotenv_path = find_dotenv(usecwd=True) or ".env"
load_dotenv(dotenv_path=dotenv_path)

# 앱의 logs/app/*.log는 logging 모듈(waitress/werkzeug 로거)에 붙은 큐 핸들러만 거치므로
# print()는 그 파일에 남지 않는다. 실거래 이력은 반드시 남아야 해서 전용 파일로 별도 기록.
_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs', 'kiwoom_trading')
os.makedirs(_LOG_DIR, exist_ok=True)

_log = logging.getLogger('kiwoom_trailing_stop')
if not _log.handlers:
    _log.setLevel(logging.INFO)
    _log.propagate = False  # 앱 root/waitress 로거로 전파 안 함 (logs/app 쪽에 중복 기록 방지)
    _formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')

    # 서버(run.py)와 CLI(-m auto_trading.kiwoom_*)가 같은 파일에 동시에 쓰므로,
    # Windows에서 다중 프로세스 로테이션이 안전한 concurrent_log_handler 사용
    #
    # 2026-08-20: 모의 계좌를 별 프로세스(run_mock.py)로 동시에 돌리기 시작하면서 로그를 나눴다.
    # 파일 쓰기 자체는 ConcurrentTimedRotatingFileHandler 라 안전하지만, 한 파일에 섞이면
    # `[손절] ...` 한 줄만 보고 어느 계좌인지 알 수 없다.
    #   real -> trading.log        (기존 파일 그대로. 180일 백업 이력 연속성 유지)
    #   mock -> trading_mock.log
    _log_name = 'trading.log' if KIWOOM_ENV == 'real' else f'trading_{KIWOOM_ENV}.log'
    from concurrent_log_handler import ConcurrentTimedRotatingFileHandler
    _file_handler = ConcurrentTimedRotatingFileHandler(
        os.path.join(_LOG_DIR, _log_name), when='midnight', backupCount=180, encoding='utf-8'
    )
    _file_handler.setFormatter(_formatter)
    _log.addHandler(_file_handler)

    _console_handler = logging.StreamHandler()
    _console_handler.setFormatter(_formatter)
    _log.addHandler(_console_handler)

# ── 청산 파라미터 (2026-08-10 손절-6%/갭5%p로 재조정 — 복리성장률 기준) ────────
# 1차 조정(-0.03→-0.05, 갭 0.02→0.03)까지는 "평균 수익률(산술평균)"만 보고 골랐는데,
# 그 뒤 실거래 47건을 라운드트립(매수~완전청산) 단위로 다시 보니 산술평균이나 손익비만으로는
# "계좌가 실제로 얼마나 빨리 크는가"를 못 잡아낸다는 게 드러났다 — 변동성이 크면 산술평균이
# 양수여도 복리로는 깎아먹는다(변동성 마모). 그래서 실제 기하평균(=매매를 순서대로 복리
# 재투자했을 때의 평균 성장률, E[log(1+r)]로 계산)을 기준으로 다시 스윕했다.
#
# 검증 방법: 2_finding_stocks_with_increased_volume.py 의 신호 로직을 최근 1년 일봉(pkl)에
# 그대로 재현해 신호 37,151건 → fire 후보 19,293건(246거래일)을 복원하고, 기본조건 + 총상승률
# 낮은순 상위 7종목(n=1,700)에 실제 청산로직을 적용. 체결은 보수적으로 가정했다
# (손절은 시가가 이미 손절선 아래면 시가 체결 = 갭하락 반영, 트레일링은 트리거가 아닌 종가 체결).
#
#   [기하평균(복리성장률), 발동5%p 고정, 손절\갭]
#              3%p      4%p      5%p      6%p      7%p      8%p
#   -5%     +0.125%  +0.101%  +0.118%  +0.176%  +0.192%  +0.198%
#   -6%     +0.153%  +0.135%  +0.159%  +0.207%  +0.237%  +0.256%   ← 그리드 안에서 전체 최고
#   -7%     +0.096%  +0.091%  +0.127%  +0.161%  +0.185%  +0.192%
#
# 갭을 넓힐수록(6→8%p) 전체 숫자는 계속 좋아지지만, 분기별로 쪼개보면 그 개선이 전부
# 2025Q3(과거)에서 나오고 가장 최근 분기(26Q3)는 넓힐수록 더 나빠진다(과적합 신호,
# -5%/3%p 26Q3 -0.92% → -6%/8%p 26Q3 -2.02%). 그래서 그리드 최고점(-6%/8%p) 대신, 전체
# 개선과 최근 분기 악화의 균형이 맞는 손절-6%/갭5%p(기하평균 +0.159%, 26Q3 -1.75%)를 택했다.
# 손절 -7% 이상은 산술평균은 버틸만해도 변동성이 더 커져 기하평균이 오히려 꺾인다.
STOP_LOSS_RATE = -0.06
# 2026-08-26 사용자 요청: 손절선에 처음 닿은 순간 즉시 시장가로 팔지 않고, 이 시간(초) 동안
# 재확인해서 그때도 여전히 손절선 이하면 판다. ⚠️ 백테스트로 검증된 값이 아니다 — 위 표의
# -6%는 '닿으면 즉시 체결'을 가정해서 나온 수치라, 대기를 넣으면 실제 성과가 달라질 수 있다
# (장점: 30초 스파이크성 하락에 덜 낚인다 / 단점: 대기 중 추가로 더 빠지면 손절선보다 더
# 깊은 손실에서 팔린다). 사이클이 30초 간격이라 60초면 최소 2번 연속 확인된다.
STOP_CONFIRM_SECONDS = 60
# 고정 목표가 사다리는 비활성화 — 익절을 트레일링에 일임한다.
# 2026-06~08 데이터(3,045건)로 실제 청산로직을 재현해 검증한 결과, 10/15/20% 사다리는
# 상승 종목을 너무 일찍 끊어 오히려 성과를 깎았다(목표가 켬 -0.21% vs 끔 +0.08%).
# 다시 켜려면 [0.10, 0.15, 0.20] 처럼 값을 채우면 된다(빈 리스트면 목표가 트리거가 아예 안 걸림).
TARGET_RATES = []
# ── 트레일링 발동/보호선 (2026-08-10 발동5%→7%, 보호선1%→3%로 재조정) ─────────
# 발동을 7%로 올리면(갭5%p 고정) 승률/손익비는 거의 그대로인데 기하평균이 +0.159%→+0.198%로
# 개선된다 — "5%를 찍고 6%를 못 넘기는 애매한 종목"이 트레일링에 덜 걸리고 손절/만기청산으로
# 자연히 정리되면서, 정말 강하게 뻗는 종목만 트레일링을 타게 되기 때문.
#
# 보호선은 발동을 올리면 같이 올려야 한다 — 트리거선 = max(고점-갭, 보호선)인데, 고점이
# 발동선(=7%)일 때 갭(5%p)만으로 나오는 자연스러운 최소값이 7%-5%=2%다. 보호선이 이보다
# 낮으면(예: 옛 값 1%) 절대 안 걸리는 죽은 코드가 된다. 보호선을 3%로 올려야 다시 의미를 갖는다
# (1년 재현 데이터 1,700건 중 87건이 실제로 이 보호선에 걸림).
TRAIL_ACTIVATE_RATE = 0.07
TRAIL_GAP = 0.05
MIN_PROFIT_FLOOR = 0.03
# 한 번이라도 +7%(TRAIL_ACTIVATE_RATE)를 찍었던 종목은 이익을 손실로 되돌리지 않도록
# 손절선을 일반 손절과 같은 폭으로 잡아 잔여 전량 청산한다.
ARMED_GIVEBACK_STOP = -0.06
STALL_GAP = 0.06  # 정체 보호: 마지막 트레일링 매도 이후 새 고점 없이 그 트리거선보다 추가로 이만큼 더 밀리면 잔여 전량 청산

# ── 트레일링 비활성화 + 보유기간 상한 (2026-08-14) ──────────────────────────
# 3년치(2023-04~2026-08, 신호 30,205건) 연도별 검증 결과 트레일링 방식이 구조적으로 손실을
# 내고 있었다. 같은 신호에 청산만 바꿔 비교(왕복비용 0.2% 반영 전 / 연도별 평균 %):
#                              2023    2024    2025    2026    전체   비용후
#   트레일링(현행,최대15일)     -1.009  -1.290  -0.455  -0.384  -0.794  -0.994
#   트레일링 파라미터 튜닝      -0.627  -0.724  -0.378  -0.362  -0.526  -0.726
#     (활성3%/gap3%/최대3일)
#   손절-6% + 5일 보유          -0.120  -0.075  +0.578  +0.705  +0.267  +0.067  ← 채택
# 트레일링은 4개 연도 '전부'에서 다른 어떤 방식보다 나빴다(현행 상회 0/4). 파라미터를 당겨도
# 마이너스를 못 벗어난다 — 이 신호의 수익이 1~3일에 몰려 있는데 트레일링은 +7%까지 올라야
# 켜지고 거기서 5%p 되돌릴 때까지 안 팔아서, 수익 구간이 끝난 뒤에 나오기 때문이다.
# 반면 '손절 -6% + 5거래일 보유'는 4개 연도 전부에서 현행을 상회하고 비용 후에도 플러스였다.
#
# ⚠️ 3년 평균 +0.267%(비용 후 +0.067%)는 '간신히 본전 위'다. 2023·2024년은 개선 후에도
#    마이너스이고, pkl에 상장폐지 종목이 빠져 있어(생존편향) 실제는 이보다 낮다.
# 되돌리려면 TRAILING_ENABLED=True로 바꾸면 원래 로직이 그대로 살아난다.
#
# ── 2026-08-20: 계좌 환경별로 청산 규칙을 분리했었다 → 2026-08-26 다시 통일 ──────
# 같은 모듈이 실전/모의 두 프로세스에서 각각 import 된다(run.py / run_mock.py).
#
# 2026-08-20~25에는 real=트레일링 OFF/5일, mock=트레일링 ON/15일로 갈라뒀다 — mock 쪽에
# fire 매수와 짝이던 '예전 방식'(트레일링)을 실계좌와 나란히 관측하려는 목적이었다.
# 그런데 fire의 현재 진입 신호(interest_v2, 상대강도)로 다시 백테스트(2026-08-25,
# auto_trading/backtest/exit_rule_swap_test.py, OOS 부트스트랩 30회, mock 실제 사이징
# 20슬롯/2,400만원/ratio0.75)한 결과:
#   현행 mock(트레일링+15일)          평균 -42.1%  범위 -46.6~-38.7%  마이너스경로 100%
#   real 방식(손절-6%, 트레일링없음) + 5일   평균  -5.6%  범위 -19.1~+4.1%   마이너스경로  90%
#   real 방식 + 15일 (★ 이번에 채택)   평균 +16.6%  범위  +0.3~+31.4%  마이너스경로   0%
# 트레일링을 빼고 보유만 5→15일로 늘린 조합이 넷 중 가장 좋았다(트레일링을 유지한 채
# 보유만 줄이면 오히려 더 나빠짐 -51.4% — 문제는 보유일수가 아니라 트레일링/분할매도
# 메커니즘 자체였다). 그래서 real/mock 둘 다 '손절 -6% + 보유 15영업일, 트레일링 없음'으로
# 통일한다. v8이 산 종목은 이 모듈이 아니라 kiwoom_v8_exit.py가 별도로 담당하므로 영향
# 없다(v8 자체 트레일링은 2026-08-26 별도 검증에서 v8 신호에 오히려 우수한 것으로 확인돼
# 그대로 유지 — strategy-ab-backtest/v8_exit_compare.py 참고).
# ⚠️ real 수동매수는 고유의 백테스트 가능한 신호가 없어(사람이 그때그때 고르므로) fire
#    신호(interest_v2)를 근사치로 썼다 — 정밀한 근거는 아니고 '현재 갖고 있는 것 중 최선'이다.
# 되돌리려면(트레일링 재검증 등) TRAILING_ENABLED=True로 바꾸면 원래 로직이 살아난다.
TRAILING_ENABLED = False
MAX_HOLD_DAYS = 15   # 이 영업일수를 넘겨 보유 중이면 잔여 전량 시장가 청산 (0 이하면 상한 없음)

# ── v8 전환용 마스터 스위치 (2026-08-19 추가) ────────────────────────────────
# v8 청산(auto_trading/kiwoom_v8_exit.py)으로 넘어갈 때 이걸 False 로 내린다.
# 둘 다 보유 종목 전체를 훑기 때문에 **동시에 켜두면 서로의 포지션을 다른 규칙으로 청산한다.**
# kiwoom_v8_exit 는 이 값이 True 면 스스로 실행을 거부한다(인터록).
LEGACY_EXIT_ENABLED = True

# ── 기업행위(액면분할·권리락)/데이터 이상 방어 ──────────────────────────────
# 액면분할 당일 아침엔 증권사가 '현재가는 분할 후 가격, 평단가·수량은 아직 조정 전'으로 주는
# 구간이 있다. 2026-07-16 티엘비(1:2 분할)에서 평단가 88,500 / 현재가 41,550으로 들어와
# rate=-53.66%로 오인, 개장 34초 만에 20주 전량 시장가 청산되며 실제 손실이 아니던 -939,000원이
# 확정된 사고가 있었다. 이런 값은 믿고 매매하면 안 되므로 아래 두 신호로 걸러 자동매매를 멈춘다.
#  - ANOMALY_DROP : 국내 증시 일일 가격제한폭이 ±30%라, 직전 관측가 대비 이 이상 급락은
#                   정상 시세 변동으로 설명되지 않는다(= 기업행위 또는 데이터 오류).
#  - ANOMALY_RATE : -6% 손절이 30초마다 도는 구조상 이만큼 깊은 손실률은 정상 경로로 도달 불가.
# 증권사가 평단가를 조정해 값이 정상 범위로 돌아오면 자동으로 매매를 재개한다.
ANOMALY_DROP = 0.35
ANOMALY_RATE = -0.25

# 모의/실전 상태·이력은 반드시 분리한다(env_path가 파일명에 _mock/_real을 붙임) — 섞이면
# 모의 계좌의 트레일링 상태·자산 기준점이 실전 매매를 조종한다. 상세는 env_path() docstring 참고.
STATE_FILE = env_path(os.path.join(os.path.dirname(__file__), 'kiwoom_trailing_state.json'))
TRADES_FILE = env_path(os.path.join(_LOG_DIR, 'trades.jsonl'))  # 실현손익 이력(승률/손익비 계산용) — 기록 누락 가능성 있음
BASELINE_FILE = env_path(os.path.join(_LOG_DIR, 'asset_baseline.json'))  # 일/주/월 시작 시점 총자산 스냅샷


# ── 대시보드용 환경별 경로 ────────────────────────────────────────────────────
# 2026-08-20: '내 계좌' 탭에서 모의/실전을 골라 볼 수 있게 하면서 추가했다.
# **자동매매(쓰기) 경로는 위 모듈 상수를 그대로 쓴다** — env를 넘기는 건 조회 경로뿐이다.
# 이렇게 분리해 두면 스케줄러 동작이 바뀌지 않는다.

def _trades_file(env: Optional[str] = None) -> str:
    if env is None:
        return TRADES_FILE
    return env_path(os.path.join(_LOG_DIR, 'trades.jsonl'), env)


def _baseline_file(env: Optional[str] = None) -> str:
    if env is None:
        return BASELINE_FILE
    return env_path(os.path.join(_LOG_DIR, 'asset_baseline.json'), env)


# KIWOOM_ENV(mock/real)에 맞는 계좌번호 쌍을 가져옴 — 모의/실전 계좌번호가 다르므로 직접 os.environ으로 읽지 않음
ACNT_NO, ACNT_PWD = get_account_credentials()


KRX_REGULAR_START = datetime.time(9, 0)
KRX_REGULAR_END = datetime.time(15, 20)       # 15:20~15:30은 KRX 종가 단일가매매(연속체결 아님)

# 넥스트트레이드(NXT, 대체거래소) 세션. 2026-08-18 실계좌 실측으로 **자동매매에서 제외**했다.
#   NXT_PREMARKET  08:00~08:50
#   NXT_AFTERMARKET 15:30~20:00
# 이 구간에 주문을 넣으면 거부된다:
#   mock : RC9000 모의투자에서는 해당업무가 제공되지 않습니다
#   real : 407022 주문이 불가능한 주문종류입니다   ← NXT는 시장가를 받지 않는다
# buy_market/sell_market은 항상 trde_tp='3'(시장가)를 보내므로(kiwoom_api.py:322-327)
# 실계좌에서도 NXT 구간은 통째로 거부됐다. 예전에는 is_market_open()이 이 구간을 열어둬서
# 청산 조건이 걸린 종목이 08:00~08:50 동안 30초마다 거부 로그를 쌓다가 09:00에야 체결됐다.
# 결과가 같으면서 로그만 더러워지므로 구간 자체를 뺀다.
# 다시 열려면 이 구간만 지정가(trde_tp='0' + 호가)로 보내는 분기가 먼저 필요하다.
NXT_PREMARKET_START = datetime.time(8, 0)
NXT_PREMARKET_END = datetime.time(8, 50)
NXT_AFTERMARKET_START = datetime.time(15, 30)
NXT_AFTERMARKET_END = datetime.time(20, 0)


def is_market_open() -> bool:
    """시장가 주문이 실제로 체결될 수 있는 구간인지. KRX 정규장만 True."""
    now = datetime.datetime.now()
    if now.weekday() >= 5:  # 토/일 제외
        return False
    return KRX_REGULAR_START <= now.time() < KRX_REGULAR_END


# run_kiwoom_trailing_stop() 전용 종료 시각. 2026-08-24: fire 자동매수를 15:19에 시작하도록
# 옮기면서, KRX_REGULAR_END(15:20)를 그대로 같이 낮추면 is_market_open()을 공유하는
# run_kiwoom_fire_buy도 같이 막혀버린다(잡이 트리거되는 순간 이미 15:19를 넘겨 있어
# 사실상 실행이 안 됨) — 그래서 trailing_stop만 별도 상수/함수로 분리했다.
TRAILING_STOP_END = datetime.time(15, 19)


def is_trailing_window_open() -> bool:
    """run_kiwoom_trailing_stop() 전용 — is_market_open()과 시작은 같고 종료만 1분 이르다."""
    now = datetime.datetime.now()
    if now.weekday() >= 5:
        return False
    return KRX_REGULAR_START <= now.time() < TRAILING_STOP_END


# fire 자동매수 전용 — 2026-08-25: 15:18/19 시장가(연속거래) 매수를 15:20~15:30 동시호가
# (단일가매매) 시장가 매수로 바꿨다. 백테스트는 '신호일 종가'를 매수가로 가정하는데
# (kiwoom_fire_strategy_mock.py 헤더 참고), 연속거래 중 시장가로 사면 그 순간의 현재가일 뿐
# 종가가 아니다 — 실측으로 15:18 매수 후 종가까지 평균 -0.9% 추가 하락이 관측됐다.
# 동시호가는 이 구간에 들어온 주문을 15:30에 KRX가 정하는 균형가격(=그날 종가) 하나로
# 전부 체결시키는 콜옥션이라, 시장가로 넣으면 정확히 '종가 매수'가 된다.
# ⚠️ is_market_open()과 별개 함수다 — is_market_open()은 15:20 이후 False라 그 함수를
#    그대로 쓰면 동시호가 구간 자체가 '장 마감'으로 막혀버린다.
CLOSING_AUCTION_START = datetime.time(15, 20)
CLOSING_AUCTION_END = datetime.time(15, 30)


def is_closing_auction_open() -> bool:
    """run_kiwoom_fire_buy() 전용 — 15:20~15:30 동시호가(단일가매매) 구간."""
    now = datetime.datetime.now()
    if now.weekday() >= 5:
        return False
    return CLOSING_AUCTION_START <= now.time() < CLOSING_AUCTION_END


def current_exchange() -> str:
    """주문을 넣을 거래소 코드.

    is_market_open()이 KRX 정규장만 통과시키므로 자동매매 경로에서는 항상 'KRX'다.
    수동 주문(--buy/--sell)은 is_market_open()을 거치지 않으므로 장 밖에서 호출될 수 있는데,
    그때 'NXT'를 보내면 407022로 거부된다. 어차피 거부될 주문이면 'KRX'로 보내
    '장종료'라는 이유가 정확히 찍히게 한다."""
    return 'KRX'


def _load_state() -> Dict:
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state: Dict):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def order_accepted(result) -> bool:
    """주문 API 응답이 '접수 성공'인지. 거래 이력을 남기기 전에 반드시 통과시켜야 한다.

    2026-08-11: 주문이 거부돼도 _record_trade가 무조건 호출돼서, 체결되지 않은 주문이
    거래 이력에 남고 손익 집계까지 오염시켰다(예: 15:53 수동매수 3건이 NXT 미지원으로
    거부됐는데 매수 1주로 기록됨).

    키움 응답 형태:
      성공 {'ord_no': '0157630', 'dmst_stex_tp': 'KRX', 'return_code': 0, 'return_msg': '모의투자 매수주문완료'}
      거부 {'return_msg': '[2000](RC9000:모의투자에서는 해당업무가 제공되지 않습니다.)', 'return_code': 20}
           {'return_msg': '[2000](RC4058:모의투자 장종료)', 'return_code': 20}
    거부 응답에는 ord_no가 없고 return_code가 0이 아니다. 둘 다 확인한다.

    ⚠️ 이건 '주문 접수' 성공이지 '체결 완료'가 아니다. 실제 체결 수량·단가는
       reconcile_fills()가 당일 체결내역(ka10076)을 조회해 사후에 채운다.
       (2026-08-11 실측 21건은 전부 전량 체결·미체결 0건이었으나 보장은 아니다.)
    """
    if not isinstance(result, dict):
        return False   # 예외로 None이 돌아온 경우 등
    try:
        if int(result.get('return_code', -1)) != 0:
            return False
    except (TypeError, ValueError):
        return False
    return bool(result.get('ord_no'))



# ── 거래비용(수수료·세금) 추정치 (KIWOOM_AUTO_TRADING.md 근거) ───────────────────
# 2026-08-26: 손절 트리거는 키움 API의 수익률(prft_rt) 필드를 쓰는데 이 값은 수수료·세금까지
# 반영된 수치라, 거래이력에 찍히는 순수 가격差 pnl/rate(-5.19%)보다 항상 먼저(-6.0%) 닿는다
# ("손절 -6%인데 왜 -5.19%로 팔렸나" 문의). 거래이력에도 수수료·세금을 명시적으로 반영한
# net_pnl/net_rate를 추가해 트리거 기준과 눈으로 봤을 때 맞아떨어지게 한다.
#   모의투자: 2026-08-11 실측(매수 0.345% 수수료만 / 매도 0.546%=수수료~0.35%+거래세0.18%)
#   실계좌  : 온라인 수수료 공시 기준 추정(매수 0.015% / 매도 0.015%+거래세0.18%=0.195%)
FEE_RATES = {
    'mock': {'buy': 0.00345, 'sell': 0.00546},
    'real': {'buy': 0.00015, 'sell': 0.00195},
}


def _fee_rate(side: str, env: Optional[str] = None) -> float:
    return FEE_RATES.get(env or KIWOOM_ENV, FEE_RATES['real'])[side]


def _record_trade(stk_cd: str, stk_nm: Optional[str], side: str, reason: str,
                   qty: int, price: float, avg_price: float, pnl: float,
                   asset_ratio: Optional[float] = None, holding_ratio: Optional[float] = None,
                   rate: Optional[float] = None, peak_rate: Optional[float] = None,
                   trigger_level: Optional[float] = None, tranche: Optional[str] = None,
                   ord_no: Optional[str] = None, env: Optional[str] = None):
    """매수/매도 1건을 거래 이력 파일에 append. 대시보드 이력/기간별 손익 집계에 사용.
    asset_ratio  : 이 거래대금(qty*price)이 총자산에서 차지한 비율 (0.05 = 5%)
    holding_ratio: 매도 시 그 종목 보유수량 대비 이번에 판 비율 (0.33 = 33%). 매수는 None.
    rate         : 매도 시점 수익률(예: -0.05). "작게 여러 번 이기고 크게 한 번 진다"처럼
                   reason만으로는 안 보이는 걸 사후 분석하려면 필요.
    peak_rate    : 이 종목이 보유 중 찍었던 최고 수익률. armed 안 된 채 바로 손절된 건지,
                   한 번 올랐다가 되돌림으로 손절된 건지 구분하는 데 쓴다.
    trigger_level: 이 매도를 발동시킨 청산선(트레일링 트리거가/손절선).
    tranche      : 3분할 중 몇 번째인지 ('1/3'~'3/3'). 트레일링/목표가에만 사용.
    ord_no       : 주문번호. reconcile_fills()가 실제 체결내역(ka10076)과 이 건을 매칭하는 키다.
                   같은 종목·같은 수량을 하루에 두 번 거래할 수 있어(예: 2026-08-11 코칩 매도 2건)
                   종목+수량으로는 매칭이 어긋난다 — 반드시 ord_no로 붙여야 한다.

    ⚠️ pnl/rate는 기존 그대로 수수료·세금 미반영(가격差만)이다 — 일별/월별 집계
       (get_pnl_summary 등)의 과거 수치와 연속성을 깨지 않기 위해 그대로 둔다.
       수수료·세금을 반영한 값은 side='sell'일 때만 net_pnl/net_rate로 추가 기록한다.

    ⚠️ price/qty는 '주문 시점 조회가'와 '주문 수량'이다. 실제 체결가·체결수량이 아니다.
       reconcile_fills()가 나중에 fill_* 필드를 채워 넣는다(아래 참고)."""
    net_pnl = net_rate = None
    if side == 'sell' and avg_price > 0 and qty > 0:
        cost = avg_price * qty
        sell_fee = price * qty * _fee_rate('sell', env)
        buy_fee = cost * _fee_rate('buy', env)
        net_pnl = round(pnl - sell_fee - buy_fee, 2)
        net_rate = net_pnl / cost

    event = {
        'ts': datetime.datetime.now().isoformat(timespec='seconds'),
        'stk_cd': stk_cd,
        'stk_nm': stk_nm or stk_cd,
        'side': side,       # 'buy' / 'sell'
        'reason': reason,   # 'stop_loss' / 'giveback_stop' / 'trailing_gap' / 'trailing_floor' / 'target' / 'stall' / 'manual' / 'fire'
        'qty': qty,
        'price': price,
        'avg_price': avg_price,
        'pnl': pnl,
        'net_pnl': net_pnl,     # 수수료·세금 반영 순손익 (side='sell'만)
        'net_rate': net_rate,   # net_pnl 기준 수익률
        'asset_ratio': asset_ratio,
        'holding_ratio': holding_ratio,
        'rate': rate,
        'peak_rate': peak_rate,
        'trigger_level': trigger_level,
        'tranche': tranche,
        'ord_no': ord_no,
    }
    try:
        with open(_trades_file(env), 'a', encoding='utf-8') as f:
            f.write(json.dumps(event, ensure_ascii=False) + '\n')
    except OSError as e:
        _log.error(f'거래 기록 저장 실패: {e}')


def _match_legacy(ev: Dict, fills: List[Dict], used: set) -> Optional[Dict]:
    """ord_no가 없는 과거 기록용 폴백 매칭 — (종목, 매수/매도, 체결수량, 시각 근접) 으로 붙인다.

    수량만으로는 어긋난다(2026-08-11 코칩 매도 2건이 둘 다 9주). 주문시각(ord_tm, HHMMSS)과
    기록 시각의 차이가 가장 작은 것을 택하고, 120초를 넘으면 포기한다.
    이미 다른 기록에 붙은 체결(used)은 재사용하지 않는다.
    """
    try:
        t = datetime.datetime.fromisoformat(ev['ts'])
    except (KeyError, ValueError):
        return None
    ev_sec = t.hour * 3600 + t.minute * 60 + t.second
    code = str(ev.get('stk_cd') or '').zfill(6)
    best, best_gap = None, None
    for f in fills:
        if id(f) in used or f['stk_cd'] != code or f['side'] != ev.get('side'):
            continue
        if f['cntr_qty'] != ev.get('qty'):
            continue
        tm = f['ord_tm']
        if len(tm) < 6:
            continue
        f_sec = int(tm[:2]) * 3600 + int(tm[2:4]) * 60 + int(tm[4:6])
        gap = abs(f_sec - ev_sec)
        if best_gap is None or gap < best_gap:
            best, best_gap = f, gap
    if best is not None and best_gap is not None and best_gap <= 120:
        return best
    return None


def reconcile_fills(dry_run: bool = False, session_date: Optional[str] = None) -> Dict:
    """당일 체결내역(ka10076)을 조회해 trades.jsonl 기록에 실제 체결 데이터를 채워 넣는다.

    왜 주문 직후가 아니라 사후 정산인가:
      1. 시장가라도 체결까지 지연이 있어 주문 직후 조회하면 미체결로 보일 수 있다.
      2. 주문 루프(fire 매수는 15:18~15:20 2분 안에 최대 20건)에 조회 호출을 끼우면
         0.35초 rate limit × 건수만큼 늘어나 KRX 마감을 넘길 위험이 생긴다.
      3. 정산이 실패해도 주문 시점 기록은 이미 남아 있어 이력이 유실되지 않는다.

    ka10076은 날짜 파라미터가 없어 '당일분'만 준다 → 반드시 같은 날(장 마감 후) 실행해야 한다.
    이미 정산된 건(fill_qty 존재)은 건너뛰므로 여러 번 돌려도 안전하다(idempotent).

    채워 넣는 필드:
      fill_qty    실제 체결수량
      fill_price  실제 체결단가
      unfilled    미체결수량 (0이 아니면 부분체결)
      cmsn / tax  수수료 / 거래세
      slippage    주문 시점 조회가 대비 체결가의 유리한 정도(%). 매수는 싸게, 매도는 비싸게
                  체결되면 양수. 시장가 주문의 실질 비용을 재는 유일한 수단이다.
      fill_pnl    체결가 기준 손익 (매도만). 기존 pnl은 조회가 기준이라 값이 다를 수 있다.
    """
    if not (ACNT_NO and ACNT_PWD):
        _log.error('[정산] 계좌 정보 미설정')
        return {'error': 'no_credentials'}
    if not os.path.exists(TRADES_FILE):
        return {'error': 'no_trades_file'}

    try:
        fills = get_filled_orders(ACNT_NO, ACNT_PWD)
    except Exception as e:
        _log.error(f'[정산] 체결내역 조회 실패: {e}')
        return {'error': str(e)}

    by_ord = {f['ord_no']: f for f in fills if f['ord_no']}
    # ka10076은 '당일분'만 준다. 기본 대상은 오늘 기록이지만, 자정을 넘겨 돌리거나 과거
    # 세션을 소급 보정할 때는 session_date로 날짜를 명시한다.
    today = session_date or datetime.date.today().isoformat()
    used = set()

    lines = []
    with open(TRADES_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                lines.append(line)

    updated = matched = skipped = no_ord_no = not_found = partial = legacy = 0
    out = []
    for line in lines:
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            out.append(line)
            continue

        # 당일 기록만 대상 (ka10076이 당일분만 주므로 과거 건은 손댈 수 없다)
        if not str(ev.get('ts', '')).startswith(today):
            out.append(line)
            continue
        if ev.get('fill_qty') is not None:
            skipped += 1
            out.append(line)
            continue
        ord_no = ev.get('ord_no')
        fill = by_ord.get(str(ord_no)) if ord_no else None
        via = 'ord_no'
        if fill is None:
            # ord_no가 없거나(과거 기록) 체결내역에서 못 찾은 경우 폴백 매칭
            fill = _match_legacy(ev, fills, used)
            via = 'legacy'
            if fill is None:
                if ord_no:
                    not_found += 1
                else:
                    no_ord_no += 1
                out.append(line)
                continue
            legacy += 1
        used.add(id(fill))
        matched += 1
        fp, fq = fill['cntr_pric'], fill['cntr_qty']
        ordered_price = float(ev.get('price') or 0)
        # 매수는 싸게, 매도는 비싸게 체결되면 유리(양수)
        slip = None
        if ordered_price > 0 and fp > 0:
            diff = (ordered_price - fp) if ev.get('side') == 'buy' else (fp - ordered_price)
            slip = round(diff / ordered_price * 100, 4)

        ev['fill_qty'] = fq
        ev['fill_price'] = fp
        ev['unfilled'] = fill['oso_qty']
        ev['cmsn'] = fill['cmsn']
        ev['tax'] = fill['tax']
        ev['slippage'] = slip
        ev['fill_src'] = via          # 'ord_no' = 정확 매칭 / 'legacy' = 종목+수량+시각 근접 매칭
        if ev.get('side') == 'sell' and ev.get('avg_price'):
            ev['fill_pnl'] = round((fp - float(ev['avg_price'])) * fq, 2)
        if fill['oso_qty']:
            partial += 1
            _log.error(f"[정산] 부분체결 감지 {ev.get('stk_nm')}({ev.get('stk_cd')}) "
                       f"ord_no={ord_no} 주문 {ev.get('qty')}주 → 체결 {fq}주, 미체결 {fill['oso_qty']}주")
        updated += 1
        out.append(json.dumps(ev, ensure_ascii=False))

    stats = {'대상일': today, '체결내역': len(fills), '이력': len(lines), '매칭': matched,
             '폴백매칭': legacy, '갱신': updated, '이미정산': skipped, 'ord_no없음': no_ord_no,
             '체결내역에없음': not_found, '부분체결': partial}
    if dry_run:
        _log.info(f'[정산-dry_run] {stats}')
        return stats

    if updated:
        tmp = TRADES_FILE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write('\n'.join(out) + '\n')
        os.replace(tmp, TRADES_FILE)   # 원자적 교체 — 쓰다가 죽어도 원본이 남는다
    _log.info(f'[정산] {stats}')
    return stats


def get_trade_history(limit: int = 200, env: Optional[str] = None) -> List[Dict]:
    """최근 거래 이력 (최신순). env로 조회할 계좌 환경을 지정(None이면 프로세스 기본값)."""
    path = _trades_file(env)
    if not os.path.exists(path):
        return []
    events = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    events.reverse()
    return events[:limit]


def _iter_sell_events(env: Optional[str] = None) -> List[Dict]:
    """trades.jsonl에서 매도(side='sell') 이벤트만 읽어 (날짜 파싱된) dict 리스트로 반환."""
    events = []
    path = _trades_file(env)
    if not os.path.exists(path):
        return events
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get('side') != 'sell':
                continue
            try:
                ev['_date'] = datetime.datetime.fromisoformat(ev['ts']).date()
            except (KeyError, ValueError):
                continue
            events.append(ev)
    return events


def get_pnl_summary(env: Optional[str] = None) -> Dict:
    """일별/주별/월별/전체 실현손익 합계·수익률 (매도 이벤트 기준)."""
    today = datetime.date.today()
    week_start = today - datetime.timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    buckets = {
        'daily': {'pnl': 0.0, 'cost': 0.0},
        'weekly': {'pnl': 0.0, 'cost': 0.0},
        'monthly': {'pnl': 0.0, 'cost': 0.0},
        'all': {'pnl': 0.0, 'cost': 0.0},
    }

    for ev in _iter_sell_events(env):
        pnl = ev.get('pnl', 0.0)
        cost = ev.get('avg_price', 0.0) * ev.get('qty', 0)
        ev_date = ev['_date']
        buckets['all']['pnl'] += pnl
        buckets['all']['cost'] += cost
        if ev_date == today:
            buckets['daily']['pnl'] += pnl
            buckets['daily']['cost'] += cost
        if ev_date >= week_start:
            buckets['weekly']['pnl'] += pnl
            buckets['weekly']['cost'] += cost
        if ev_date >= month_start:
            buckets['monthly']['pnl'] += pnl
            buckets['monthly']['cost'] += cost

    return {
        key: {'pnl': b['pnl'], 'rate': (b['pnl'] / b['cost']) if b['cost'] > 0 else 0.0}
        for key, b in buckets.items()
    }


def get_win_loss_ratio(env: Optional[str] = None) -> Optional[float]:
    """손익비(Risk-Reward Ratio) = 실현 평균이익 / 실현 평균손실(절대값). 매도 이력 전체 기준.
    손실 거래가 하나도 없으면 None(무한대 취급)."""
    sells = _iter_sell_events(env)
    wins = [ev['pnl'] for ev in sells if ev.get('pnl', 0.0) > 0]
    losses = [-ev['pnl'] for ev in sells if ev.get('pnl', 0.0) < 0]
    if not losses:
        return None
    if not wins:
        return 0.0
    avg_win = sum(wins) / len(wins)
    avg_loss = sum(losses) / len(losses)
    return avg_win / avg_loss


def _load_baseline(env: Optional[str] = None) -> Dict:
    path = _baseline_file(env)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_baseline(data: Dict, env: Optional[str] = None):
    with open(_baseline_file(env), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _ensure_baseline(current_total_asset: float, env: Optional[str] = None) -> Dict:
    """일/주/월이 바뀌면 새 기준선을 기록. 기준선은 '전일 마지막 관측 자산'(사실상 전일 종가 자산)을
    사용한다 — 오늘 첫 조회 시점 자산으로 잡으면 그 전에 발생한 수익/손실이 0으로 묻히기 때문.
    API 오류로 총자산이 0/음수로 들어오면 기준선을 건드리지 않는다."""
    data = _load_baseline(env)
    if not current_total_asset or current_total_asset <= 0:
        return data

    today = datetime.date.today()
    week_start = today - datetime.timedelta(days=today.weekday())
    month_key = today.strftime('%Y-%m')
    changed = False

    # 새 기간의 시작 기준선 = 직전(전일)까지 관측된 마지막 자산. 없으면 현재값으로 초기화.
    rollover_base = data.get('last_asset') or current_total_asset

    if data.get('daily_date') != today.isoformat():
        data['daily_date'] = today.isoformat()
        data['daily_start'] = rollover_base
        changed = True
    if data.get('weekly_date') != week_start.isoformat():
        data['weekly_date'] = week_start.isoformat()
        data['weekly_start'] = rollover_base
        changed = True
    if data.get('monthly_date') != month_key:
        data['monthly_date'] = month_key
        data['monthly_start'] = rollover_base
        changed = True

    # 과거 버그(API 오류 시 0.0 저장) 복구: 기준선이 0/None이면 복원
    for key in ('daily_start', 'weekly_start', 'monthly_start'):
        if not data.get(key) or data[key] <= 0:
            data[key] = rollover_base
            changed = True

    if data.get('last_asset') != current_total_asset:
        data['last_asset'] = current_total_asset
        data['last_asset_date'] = today.isoformat()
        changed = True

    if changed:
        _save_baseline(data, env)
    return data


def record_cash_transfer(amount: float, note: str = '') -> Dict:
    """계좌 입출금(직접 이체)을 손익 기준선에 반영한다. 입금은 양수, 출금은 음수.

    자산기준 손익은 '현재 총자산 - 기준 자산'이라 입출금을 매매 손익과 구분하지 못한다.
    실제로 2026-08-14 실계좌에 259,052원을 입금했더니 오늘 손익이 +260,898원(+15.09%)으로
    잡혔다(같은 시각 체결기준 손익은 +1,846원). 키움 API에 입출금 조회가 없어 자동 감지가
    안 되므로, 이체할 때마다 이 함수로 기준선을 같이 올려/내려 주어야 한다.

        venv/Scripts/python.exe -m auto_trading.kiwoom_trailing_stop --transfer 259052
        venv/Scripts/python.exe -m auto_trading.kiwoom_trailing_stop --transfer -100000 --note "출금"

    기준선에 amount를 더하면 (현재자산 - (기준선+입금액)) 이 되어 입금분이 손익에서 빠진다.
    """
    data = _load_baseline()
    before = {k: data.get(k) for k in ('daily_start', 'weekly_start', 'monthly_start')}

    for key in ('daily_start', 'weekly_start', 'monthly_start'):
        if data.get(key):
            data[key] = float(data[key]) + amount

    # last_asset도 같이 올려야 다음 날 기준선 롤오버(rollover_base)가 어긋나지 않는다.
    if data.get('last_asset'):
        data['last_asset'] = float(data['last_asset']) + amount

    # 감사용 이력 — 나중에 "이 기준선이 왜 이 값인가"를 되짚을 수 있게 남긴다.
    data.setdefault('transfers', []).append({
        'ts': datetime.datetime.now().isoformat(timespec='seconds'),
        'amount': amount,
        'note': note,
    })
    _save_baseline(data)

    _log.info(f'[입출금반영] {amount:+,.0f}원 {note} — 기준선 '
              f'일 {before["daily_start"]:,.0f}→{data["daily_start"]:,.0f} / '
              f'주 {before["weekly_start"]:,.0f}→{data["weekly_start"]:,.0f} / '
              f'월 {before["monthly_start"]:,.0f}→{data["monthly_start"]:,.0f}')
    return data


def get_asset_based_pnl(current_total_asset: float, env: Optional[str] = None) -> Dict:
    """실제 총자산 변동 기준 일/주/월 손익. 거래 누락·수수료·세금과 무관하게 항상 정확함
    (trades.jsonl 기반 get_pnl_summary()의 실현손익 집계는 기록되지 않은 거래가 있으면 틀릴 수 있음)."""
    zero = {'pnl': 0.0, 'rate': 0.0}
    if not current_total_asset or current_total_asset <= 0:
        # API 오류 등으로 총자산이 비정상이면 기준선을 오염시키지 않고 0 반환
        return {'daily': dict(zero), 'weekly': dict(zero), 'monthly': dict(zero)}

    baseline = _ensure_baseline(current_total_asset, env)

    def calc(start):
        start = start if start and start > 0 else current_total_asset
        pnl = current_total_asset - start
        rate = (pnl / start) if start else 0.0
        return {'pnl': pnl, 'rate': rate}

    return {
        'daily': calc(baseline.get('daily_start')),
        'weekly': calc(baseline.get('weekly_start')),
        'monthly': calc(baseline.get('monthly_start')),
    }


def _fresh_position_state(qty: int) -> Dict:
    return {
        'original_qty': qty,
        'tranche_qty': max(1, qty // 3),
        'remaining_qty': qty,
        'peak_rate': None,
        'last_sold_peak': None,
        'thirds_sold': 0,
        'target_idx': 0,  # 다음에 확인할 TARGET_RATES 인덱스
        'exited': False,
        'last_price': None,  # 직전 사이클 관측 현재가 (기업행위 급락 감지용)
        'halted': False,     # 데이터 이상으로 자동매매 정지된 상태인지
        # MAX_HOLD_DAYS 계산 기준일. 실제 매수일이 아니라 '이 상태를 처음 만든 날'이다 —
        # 추가매수로 상태가 리셋되면 보유기간도 그 시점부터 다시 센다(평단가가 바뀌었으므로
        # 손절선과 마찬가지로 새 기준으로 보는 게 맞다).
        'entry_date': datetime.date.today().isoformat(),
    }


def _held_business_days(entry_date: Optional[str]) -> Optional[int]:
    """entry_date 이후 지난 영업일(월~금) 수. 공휴일은 반영하지 않으므로 실제 거래일보다 크거나
    같다 — 상한에 약간 일찍 걸릴 수 있는데, 늦게 파는 것보다 안전한 방향이라 그대로 둔다."""
    if not entry_date:
        return None
    try:
        start = datetime.date.fromisoformat(entry_date)
    except (TypeError, ValueError):
        return None
    today = datetime.date.today()
    if today <= start:
        return 0
    days = 0
    cur = start
    while cur < today:
        cur += datetime.timedelta(days=1)
        if cur.weekday() < 5:   # 0=월 ~ 4=금
            days += 1
    return days


def _detect_data_anomaly(pos_state: Dict, rate: float, cur_price: float) -> Optional[str]:
    """증권사 데이터가 기업행위(액면분할·권리락) 등으로 어긋났는지 판단. 사유 문자열 또는 None."""
    if cur_price <= 0:
        return f'현재가가 {cur_price}원으로 조회됨 (시세 조회 실패)'

    last_price = pos_state.get('last_price')
    if last_price and cur_price <= last_price * (1 - ANOMALY_DROP):
        return (f'직전 관측가 {last_price:,.0f}원 → 현재가 {cur_price:,.0f}원 '
                f'({cur_price / last_price - 1:.1%}, 일일 가격제한폭 ±30% 초과)')

    if rate <= ANOMALY_RATE:
        return (f'손실률 {rate:.2%} (손절선 {STOP_LOSS_RATE:.1%}가 30초마다 도는 구조상 '
                f'정상적으로는 도달할 수 없는 값)')

    return None


def evaluate_and_trade(holding: Dict, pos_state: Optional[Dict], total_asset: float = 0.0) -> Dict:
    """holding 1건 평가 후 필요 시 매도 실행. 갱신된 pos_state 반환.
    total_asset: 자산기준 거래비율(asset_ratio) 계산용 총자산. 0/미상이면 비율 계산 생략."""
    stk_cd = holding['stk_cd']
    stk_nm = holding.get('stk_nm') or stk_cd
    qty = holding['qty']
    rate = holding['profit_rate']
    avg_price = holding['avg_price']
    cur_price = holding['cur_price']

    # 신규 종목/완전 청산 후 재진입은 물론, 추가 매수로 수량이 늘어난 경우도 상태를 새로 만든다.
    # rate(수익률)는 Kiwoom이 매번 평단가 기준으로 다시 계산해서 내려주므로, 추가매수로 평단가가
    # 바뀌면 peak_rate/target_idx 같은 %기반 진행상태는 새 평단가와 더 이상 같은 척도가 아니게 됨
    # → 보존하지 않고 새 평단가 기준으로 사다리/트레일링을 처음부터 다시 평가한다.
    if pos_state is None or pos_state.get('exited') or qty > pos_state.get('remaining_qty', 0):
        # 액면분할이 반영되면 수량이 늘어 여기서 상태가 리셋되는데, 분할 감지에 쓰는 직전 관측가와
        # 정지 상태까지 같이 날아가면 바로 다음 사이클에서 이상 징후를 놓친다. 계속 보유 중인
        # 포지션일 때만 넘겨받는다 (완전 청산 후 재진입은 예전 가격과 무관하므로 제외).
        carry_over = {}
        if pos_state is not None and not pos_state.get('exited'):
            carry_over = {
                'last_price': pos_state.get('last_price'),
                'halted': pos_state.get('halted', False),
                'halt_reason': pos_state.get('halt_reason'),
            }
        pos_state = _fresh_position_state(qty)
        pos_state.update({k: v for k, v in carry_over.items() if v})
    elif qty < pos_state['remaining_qty']:
        # 수동 매도 등으로 외부에서 수량이 줄어든 경우, 고점/분할 진행 상태는 유지하고 수량만 동기화
        pos_state['remaining_qty'] = qty

    if pos_state['remaining_qty'] <= 0:
        pos_state['exited'] = True
        return pos_state

    # 이전 버전(단일 목표가 target_hit) 상태 파일과의 호환: target_idx가 없으면 마이그레이션
    if 'target_idx' not in pos_state:
        pos_state['target_idx'] = 1 if pos_state.get('target_hit') else 0

    # MAX_HOLD_DAYS 도입(2026-08-14) 이전에 만들어진 상태에는 entry_date가 없다. 실제 매수일을
    # 알 수 없으므로 '오늘 처음 본 것'으로 잡는다 — 보유상한이 즉시 발동해 예상치 못한 전량
    # 청산이 일어나는 것보다, 오늘부터 다시 세는 쪽이 안전하다.
    if not pos_state.get('entry_date'):
        pos_state['entry_date'] = datetime.date.today().isoformat()

    # 0) 기업행위/데이터 이상 방어 — 손절·트레일링 등 어떤 매도보다 먼저 평가한다.
    #    값이 신뢰할 수 없으면 매도하지 않고 경고만 남긴 뒤 그대로 보유 (실손실 확정 방지).
    anomaly = _detect_data_anomaly(pos_state, rate, cur_price)
    if anomaly:
        if not pos_state.get('halted'):  # 30초마다 같은 경고가 쌓이지 않도록 최초 1회만
            _log.error(f'[데이터이상-자동매매정지] {stk_nm}({stk_cd}) {anomaly} | '
                       f'평단가={avg_price:,.0f}원 현재가={cur_price:,.0f}원 {qty}주. '
                       f'액면분할/권리락이면 증권사 평단가 조정 후 자동 재개됨. '
                       f'아니면 수동 확인 필요 (자동 매도 안 함).')
        pos_state['halted'] = True
        pos_state['halt_reason'] = anomaly
        pos_state['last_price'] = cur_price
        return pos_state

    if pos_state.get('halted'):
        _log.info(f'[자동매매재개] {stk_nm}({stk_cd}) 데이터 정상화 확인 '
                  f'(rate={rate:.2%} 평단가={avg_price:,.0f}원 현재가={cur_price:,.0f}원)')
        pos_state['halted'] = False
        pos_state.pop('halt_reason', None)

    pos_state['last_price'] = cur_price

    # 1) 손절 — 다른 조건과 무관하게 잔여 수량 전량 즉시 청산.
    #    단, 한 번이라도 +5%를 찍어 트레일링이 활성화됐던 종목은 이익을 손실로 되돌리지 않도록
    #    손절선을 -3%(ARMED_GIVEBACK_STOP)로 좁힌다. peak_rate는 이전 사이클까지 누적된 값이라
    #    이번 사이클의 고점 갱신(2번) 이전에 판단해도 문제 없음.
    was_armed = (pos_state.get('peak_rate') is not None
                 and pos_state['peak_rate'] >= TRAIL_ACTIVATE_RATE)
    stop_level = ARMED_GIVEBACK_STOP if was_armed else STOP_LOSS_RATE

    if rate <= stop_level:
        # 2026-08-26: 즉시 체결하지 않고 STOP_CONFIRM_SECONDS(60초) 재확인 — 최초 도달 시각을
        # pos_state에 남겨두고, 그 시간이 지난 뒤에도 여전히 손절선 이하일 때만 실제로 판다.
        # 도중에 손절선 위로 회복하면(else 분기) 관찰을 취소한다.
        now = datetime.datetime.now()
        since_raw = pos_state.get('stop_watch_since')
        since_dt = None
        if since_raw:
            try:
                since_dt = datetime.datetime.fromisoformat(since_raw)
            except ValueError:
                since_dt = None
        if since_dt is None:
            pos_state['stop_watch_since'] = now.isoformat()
            _log.info(f'[손절관찰] {stk_nm}({stk_cd}) rate={rate:.2%} (손절선 {stop_level:.1%}) 최초 도달 — '
                      f'{STOP_CONFIRM_SECONDS}초 재확인 대기')
            return pos_state
        if (now - since_dt).total_seconds() < STOP_CONFIRM_SECONDS:
            return pos_state

        sell_qty = pos_state['remaining_qty']
        pnl = (cur_price - avg_price) * sell_qty
        trade_value = cur_price * sell_qty
        asset_ratio = (trade_value / total_asset) if total_asset > 0 else 0.0
        holding_ratio = 1.0  # 손절은 항상 잔여 전량
        label = '되돌림손절' if was_armed else '손절'
        peak_txt = f' 고점={pos_state["peak_rate"]:.2%}' if was_armed else ''
        res = sell_market(stk_cd, sell_qty, dmst_stex_tp=current_exchange())
        if not order_accepted(res):
            # 주문이 거부됐으면 이력도 남기지 않고 상태도 건드리지 않는다 —
            # exited로 바꿔버리면 이 종목이 다음 사이클부터 관리 대상에서 빠져 무방비가 된다.
            # 30초 뒤 사이클에서 같은 조건으로 재시도된다.
            _log.error(f'[{label}-주문거부] {stk_nm}({stk_cd}) rate={rate:.2%} {sell_qty}주 → {res} '
                       f'(이력 미기록, 다음 사이클에 재시도)')
            return pos_state
        _log.info(f'[{label}] {stk_nm}({stk_cd}) rate={rate:.2%}{peak_txt} (손절선 {stop_level:.1%}) '
                  f'매입가={avg_price:,.0f}원 현재가={cur_price:,.0f}원 '
                  f'{sell_qty}주 전량 청산, 손익={pnl:+,.0f}원, 거래대금={trade_value:,.0f}원(자산의 {asset_ratio:.1%}) '
                  f'ord_no={res.get("ord_no")}')
        _record_trade(stk_cd, stk_nm, 'sell', 'giveback_stop' if was_armed else 'stop_loss',
                      sell_qty, cur_price, avg_price, pnl,
                      asset_ratio=asset_ratio, holding_ratio=holding_ratio,
                      rate=rate, peak_rate=pos_state.get('peak_rate'), trigger_level=stop_level,
                      ord_no=res.get('ord_no'))
        pos_state['remaining_qty'] = 0
        pos_state['exited'] = True
        return pos_state
    elif pos_state.get('stop_watch_since') is not None:
        _log.info(f'[손절관찰해제] {stk_nm}({stk_cd}) rate={rate:.2%} 로 회복 — 재확인 취소')
        pos_state['stop_watch_since'] = None

    # 1-2) 보유기간 상한 — 손절 다음, 트레일링보다 먼저 본다.
    #      이 신호의 수익은 1~3일에 몰려 있고 그 뒤로 소멸한다(3년 검증: 1일 +0.106% /
    #      3일 +0.085% / 10일 -0.918% / 20일 -1.366%). 오래 들고 있는 것 자체가 손실이다.
    held = _held_business_days(pos_state.get('entry_date')) if MAX_HOLD_DAYS > 0 else None
    if held is not None and held >= MAX_HOLD_DAYS:
        sell_qty = pos_state['remaining_qty']
        pnl = (cur_price - avg_price) * sell_qty
        trade_value = cur_price * sell_qty
        asset_ratio = (trade_value / total_asset) if total_asset > 0 else 0.0
        res = sell_market(stk_cd, sell_qty, dmst_stex_tp=current_exchange())
        if not order_accepted(res):
            _log.error(f'[보유상한-주문거부] {stk_nm}({stk_cd}) rate={rate:.2%} {sell_qty}주 → {res} '
                       f'(이력 미기록, 상태 유지, 다음 사이클에 재시도)')
            return pos_state
        _log.info(f'[보유상한청산] {stk_nm}({stk_cd}) rate={rate:.2%} 보유 {held}영업일'
                  f'(상한 {MAX_HOLD_DAYS}일, 진입 {pos_state.get("entry_date")}) '
                  f'매입가={avg_price:,.0f}원 현재가={cur_price:,.0f}원 '
                  f'{sell_qty}주 전량 청산, 손익={pnl:+,.0f}원, '
                  f'거래대금={trade_value:,.0f}원(자산의 {asset_ratio:.1%}) ord_no={res.get("ord_no")}')
        _record_trade(stk_cd, stk_nm, 'sell', 'max_hold', sell_qty, cur_price, avg_price, pnl,
                      asset_ratio=asset_ratio, holding_ratio=1.0, rate=rate,
                      peak_rate=pos_state.get('peak_rate'), ord_no=res.get('ord_no'))
        pos_state['remaining_qty'] = 0
        pos_state['exited'] = True
        return pos_state

    # TRAILING_ENABLED=False면 아래 트레일링/목표가/정체보호를 통째로 건너뛴다.
    # (3년 검증에서 트레일링이 4개 연도 전부 손실이었다 — 위 상수 주석 참고)
    if not TRAILING_ENABLED:
        return pos_state

    # 2) 트레일링 고점 갱신 (+5% 이상에서만 추적 시작)
    if rate >= TRAIL_ACTIVATE_RATE:
        pos_state['peak_rate'] = rate if pos_state['peak_rate'] is None else max(pos_state['peak_rate'], rate)

    peak_rate = pos_state['peak_rate']
    trailing_armed = peak_rate is not None and peak_rate >= TRAIL_ACTIVATE_RATE
    new_peak_since_last_sale = trailing_armed and (
        pos_state['last_sold_peak'] is None or peak_rate > pos_state['last_sold_peak']
    )
    trigger_level = max(peak_rate - TRAIL_GAP, MIN_PROFIT_FLOOR) if trailing_armed else None
    trailing_trigger = bool(trigger_level is not None and new_peak_since_last_sale and rate <= trigger_level)
    # 트레일링이 (고점-갭)이 아니라 보호선(MIN_PROFIT_FLOOR)에 걸려서 트리거된 경우 — 로그 구분 +
    # 아래에서 1/3 대신 잔여 전량 매도로 처리하는 데 쓴다.
    # 2026-08-04엔 "보호선 걸리면 전량청산" → "1/3만 매도"로 바꾼 적 있다(당시 발동5%/보호선1%라
    # 거의 모든 트레일링이 보호선에 걸려, 약하게 오른 종목도 무조건 전량 매도돼버렸음 — 지엔씨에너지
    # 고점 5.18% → 매수 12분 만에 전량 종료 사례). 2026-08-10 발동7%/보호선3%로 같이 올리면서
    # 재검증한 결과, 지금은 보호선이 "발동 직후 바로 꺾이는 약한 모멘텀"에만 선택적으로 걸리고
    # (1년 재현 데이터 1,700건 중 87건), 이 경우 1/3만 팔고 남기는 것보다 전량 정리가 승률·기하평균·
    # 최근 분기 안정성 모두 더 낫다(기하평균 +0.199%→+0.220%). 그래서 다시 전량청산으로 되돌렸다.
    trailing_floor_trigger = trailing_trigger and trigger_level <= MIN_PROFIT_FLOOR + 1e-9

    # 3) 목표가(+10/15/20%) — 단계별로 최초 1회씩 트리거 (도달한 가장 높은 단계까지 한 번에 반영)
    target_idx = pos_state['target_idx']
    target_trigger = target_idx < len(TARGET_RATES) and rate >= TARGET_RATES[target_idx]
    target_level = TARGET_RATES[target_idx] if target_trigger else None

    if pos_state['thirds_sold'] < 3 and (trailing_trigger or target_trigger):
        # 보호선 트리거는 1/3 분할이 아니라 잔여 전량을 정리한다 (위 trailing_floor_trigger 주석 참고).
        # 주문이 거부될 수 있으므로 상태(thirds_sold 등)는 '접수 성공' 확인 후에만 반영한다.
        # 미리 올려놓고 거부되면 분할 횟수만 소진돼 남은 물량이 관리에서 빠진다.
        floor_full_exit = trailing_floor_trigger and not target_trigger
        if floor_full_exit:
            next_thirds = 3
            sell_qty = pos_state['remaining_qty']
        else:
            next_thirds = pos_state['thirds_sold'] + 1
            # 마지막(3번째) 트리거는 나눗셈 나머지까지 포함해 잔여 수량 전부 정리
            sell_qty = pos_state['remaining_qty'] if next_thirds >= 3 \
                else min(pos_state['tranche_qty'], pos_state['remaining_qty'])

        if sell_qty > 0:
            pnl = (cur_price - avg_price) * sell_qty
            trade_value = cur_price * sell_qty
            asset_ratio = (trade_value / total_asset) if total_asset > 0 else 0.0
            holding_ratio = sell_qty / pos_state['remaining_qty'] if pos_state['remaining_qty'] > 0 else 0.0
            res = sell_market(stk_cd, sell_qty, dmst_stex_tp=current_exchange())
            if not order_accepted(res):
                _log.error(f'[트레일링/목표가-주문거부] {stk_nm}({stk_cd}) rate={rate:.2%} '
                           f'{sell_qty}주 → {res} (이력 미기록, 상태 유지, 다음 사이클에 재시도)')
                return pos_state
            pos_state['thirds_sold'] = next_thirds
            tranche_txt = f'{pos_state["thirds_sold"]}/3'
            if target_trigger:
                reason = f'목표가{target_level:.0%}'
                reason_key = 'target'
            elif trailing_floor_trigger:
                reason = '트레일링-보호선'
                reason_key = 'trailing_floor'  # 트리거선이 보호선(+1%)에 붙어 발동 — 갭 트리거보다 이익이 작음
            else:
                reason = '트레일링'
                reason_key = 'trailing_gap'    # 고점-갭 트리거선에서 정상 발동
            trigger_txt = f'{trigger_level:.2%}' if trigger_level is not None else 'N/A'
            peak_txt2 = f'{peak_rate:.2%}' if peak_rate is not None else 'N/A'
            _log.info(f'[{reason} {tranche_txt}차] {stk_nm}({stk_cd}) rate={rate:.2%} '
                      f'peak={peak_txt2} 트리거선={trigger_txt} 매입가={avg_price:,.0f}원 현재가={cur_price:,.0f}원 '
                      f'{sell_qty}주 매도, 손익={pnl:+,.0f}원, 거래대금={trade_value:,.0f}원'
                      f'(자산의 {asset_ratio:.1%}, 보유수량의 {holding_ratio:.0%}), 잔여 {pos_state["remaining_qty"] - sell_qty}주 '
                      f'ord_no={res.get("ord_no")}')
            _record_trade(stk_cd, stk_nm, 'sell', reason_key,
                           sell_qty, cur_price, avg_price, pnl,
                           asset_ratio=asset_ratio, holding_ratio=holding_ratio,
                           rate=rate, peak_rate=peak_rate, trigger_level=trigger_level, tranche=tranche_txt,
                           ord_no=res.get('ord_no'))
            pos_state['remaining_qty'] -= sell_qty
        else:
            # 팔 수량이 0인 경우엔 주문 자체가 없으므로 분할 횟수만 기존과 동일하게 반영
            pos_state['thirds_sold'] = next_thirds

        if target_trigger:
            pos_state['target_idx'] += 1
        if trailing_trigger:
            pos_state['last_sold_peak'] = peak_rate

        if pos_state['remaining_qty'] <= 0 or pos_state['thirds_sold'] >= 3:
            pos_state['exited'] = True

    # 4) 정체 보호 — 트레일링이 한 번 나간 뒤(last_sold_peak 존재) 그 이후 새 고점 없이 그때 쓰인
    # 트리거선보다 STALL_GAP만큼 더 밀리면 잔여 전량 청산. 트레일링/목표가가 이번 사이클에 이미
    # 매도했다면(위 블록) 여기는 평가하지 않는다.
    elif pos_state['thirds_sold'] < 3 and pos_state['remaining_qty'] > 0 and pos_state['last_sold_peak'] is not None:
        gated = peak_rate is None or peak_rate <= pos_state['last_sold_peak']
        if gated:
            trig_used = max(pos_state['last_sold_peak'] - TRAIL_GAP, MIN_PROFIT_FLOOR)
            if rate <= trig_used - STALL_GAP:
                sell_qty = pos_state['remaining_qty']
                pnl = (cur_price - avg_price) * sell_qty
                trade_value = cur_price * sell_qty
                asset_ratio = (trade_value / total_asset) if total_asset > 0 else 0.0
                res = sell_market(stk_cd, sell_qty, dmst_stex_tp=current_exchange())
                if not order_accepted(res):
                    _log.error(f'[정체보호-주문거부] {stk_nm}({stk_cd}) rate={rate:.2%} {sell_qty}주 → {res} '
                               f'(이력 미기록, 상태 유지, 다음 사이클에 재시도)')
                    return pos_state
                _log.info(f'[정체보호전량청산] {stk_nm}({stk_cd}) rate={rate:.2%} 직전고점={pos_state["last_sold_peak"]:.2%} '
                          f'트리거선={trig_used - STALL_GAP:.2%} 매입가={avg_price:,.0f}원 현재가={cur_price:,.0f}원 {sell_qty}주 전량 청산, '
                          f'손익={pnl:+,.0f}원, 거래대금={trade_value:,.0f}원(자산의 {asset_ratio:.1%}) '
                          f'ord_no={res.get("ord_no")}')
                _record_trade(stk_cd, stk_nm, 'sell', 'stall', sell_qty, cur_price, avg_price, pnl,
                              asset_ratio=asset_ratio, holding_ratio=1.0,
                              rate=rate, peak_rate=pos_state['last_sold_peak'],
                              trigger_level=trig_used - STALL_GAP, ord_no=res.get('ord_no'))
                pos_state['remaining_qty'] = 0
                pos_state['exited'] = True

    return pos_state


def run_cycle():
    if not LEGACY_EXIT_ENABLED:
        return          # v8 청산으로 전환됨 (kiwoom_v8_exit.py)
    if not (ACNT_NO and ACNT_PWD):
        _log.error('KIWOOM_ACNT_NO / KIWOOM_ACNT_PWD가 .env에 설정되지 않음')
        return

    holdings, summary = get_holdings_and_summary(ACNT_NO, ACNT_PWD)
    if not holdings:
        return
    total_asset = summary['total_asset']

    state = _load_state()
    held_codes = set()

    # v8 이 매수한 종목은 kiwoom_v8_exit 가 담당한다(ATR 샹들리에 + 트레일링 절반 + 익절 +20%).
    # 여기서 제외하지 않으면 같은 포지션을 두 모듈이 서로 다른 규칙으로 팔아버린다.
    # 조회 실패 시에는 중복 매도 위험이 있으므로 기존 청산을 아예 건너뛴다(보수적 선택).
    try:
        from auto_trading import kiwoom_v8_strategy as _v8
        v8_owned = _v8.v8_owned_codes()
    except Exception as e:
        _log.error(f'v8 소유권 조회 실패 — 중복 매도를 막기 위해 기존 청산을 건너뜀: {e}')
        return

    for holding in holdings:
        stk_cd = holding['stk_cd']
        if stk_cd in v8_owned:
            continue
        held_codes.add(stk_cd)
        state[stk_cd] = evaluate_and_trade(holding, state.get(stk_cd), total_asset)

    # 더 이상 보유하지 않는(전량 매도/청산된) 종목은 상태 정리
    for stk_cd in list(state.keys()):
        if stk_cd not in held_codes:
            del state[stk_cd]

    _save_state(state)


def log_account_summary():
    if not (ACNT_NO and ACNT_PWD):
        _log.error('KIWOOM_ACNT_NO / KIWOOM_ACNT_PWD가 .env에 설정되지 않음')
        return
    s = get_account_summary(ACNT_NO, ACNT_PWD)

    # 실제 총자산 변동 기준(거래 기록 누락·수수료·세금과 무관하게 항상 정확함, 미실현 손익 포함)
    asset_pnl = get_asset_based_pnl(s['total_asset'])
    # 체결(완료된 매도) 기준 실현손익 — 대시보드 '거래 수익' 태그와 동일 소스. 보유종목 평가변동은 반영 안 됨
    trade_pnl = get_pnl_summary()

    ratio = get_win_loss_ratio()
    ratio_str = f'{ratio:.2f}' if ratio is not None else '손실없음'

    _log.info(
        f'[계좌현황] 총자산={s["total_asset"]:,.0f}원 매입={s["tot_pur_amt"]:,.0f}원 '
        f'평가={s["tot_evlt_amt"]:,.0f}원 손익={s["tot_evlt_pl"]:+,.0f}원 수익률={s["tot_prft_rt"]:+.2%} '
        # f'\n오늘손익(자산기준)={asset_pnl["daily"]["pnl"]:+,.0f}원({asset_pnl["daily"]["rate"]:+.2%}) '
        # f'주간손익(자산기준)={asset_pnl["weekly"]["pnl"]:+,.0f}원({asset_pnl["weekly"]["rate"]:+.2%}) '
        # f'월간손익(자산기준)={asset_pnl["monthly"]["pnl"]:+,.0f}원({asset_pnl["monthly"]["rate"]:+.2%}) '
        f'\n오늘손익(체결기준)={trade_pnl["daily"]["pnl"]:+,.0f}원({trade_pnl["daily"]["rate"]:+.2%}) '
        f'주간손익(체결기준)={trade_pnl["weekly"]["pnl"]:+,.0f}원({trade_pnl["weekly"]["rate"]:+.2%}) '
        f'월간손익(체결기준)={trade_pnl["monthly"]["pnl"]:+,.0f}원({trade_pnl["monthly"]["rate"]:+.2%}) '
        f'손익비={ratio_str}'
    )


def manual_buy(stk_cd: str, qty: Optional[int] = None, env: Optional[str] = None):
    """수동 시장가 매수. qty 생략 시 가용 현금(총자산-보유종목평가금액) 전액으로 매수.

    env: 'mock' | 'real' | None(프로세스 기본). 대시보드에서 계좌를 골라 주문할 때 쓴다 —
    화면에 모의 계좌를 띄워놓고 실전에 주문이 나가는 사고를 막기 위해 조회와 같은 env를 넘긴다.
    """
    acnt_no, acnt_pwd = get_account_credentials(env)
    if not (acnt_no and acnt_pwd):
        _log.error(f'[수동매수] 계좌 정보 미설정 (env={env or KIWOOM_ENV})')
        return

    price, stk_nm = get_current_price_and_name(stk_cd, env=env)
    if price <= 0:
        _log.error(f'[수동매수] {stk_cd} 현재가 조회 실패')
        return

    s = get_account_summary(acnt_no, acnt_pwd, env)
    total_asset = s['total_asset']
    if qty is None:
        cash = total_asset - s['tot_evlt_amt']
        qty = int(cash // price)

    if qty <= 0:
        _log.error(f'[수동매수] {stk_nm}({stk_cd}) 현재가={price:,}원, 매수 가능 수량 0')
        return

    trade_value = qty * price
    asset_ratio = (trade_value / total_asset) if total_asset > 0 else 0.0

    result = buy_market(stk_cd, qty, dmst_stex_tp=current_exchange(), env=env)
    if not order_accepted(result):
        # 모의투자는 NXT 주문(프리/애프터마켓)과 장종료 후 주문을 거부한다 → 이력에 남기지 않는다.
        _log.error(f'[수동매수-주문거부] {stk_nm}({stk_cd}) 현재가={price:,}원 {qty}주 → {result} '
                   f'(거래 이력에 기록하지 않음)')
        return result
    _log.info(f'[수동매수:{env or KIWOOM_ENV}] {stk_nm}({stk_cd}) 현재가={price:,}원 {qty}주 → {result}, '
              f'거래대금={trade_value:,.0f}원(자산의 {asset_ratio:.1%})')
    _record_trade(stk_cd, stk_nm, 'buy', 'manual', qty, price, price, 0.0, asset_ratio=asset_ratio,
                  ord_no=result.get('ord_no'), env=env)
    return result


def manual_sell(stk_cd: str, qty: int, env: Optional[str] = None):
    """수동 시장가 매도. qty는 실제 보유수량으로 자동 제한됨.

    env: 'mock' | 'real' | None(프로세스 기본). manual_buy()와 같은 이유로 조회와 동일한
    env를 받는다 — 화면의 계좌와 주문이 나가는 계좌가 어긋나면 안 된다.
    """
    acnt_no, acnt_pwd = get_account_credentials(env)
    if not (acnt_no and acnt_pwd):
        _log.error(f'[수동매도] 계좌 정보 미설정 (env={env or KIWOOM_ENV})')
        return

    holdings, summary = get_holdings_and_summary(acnt_no, acnt_pwd, env)
    match = next((h for h in holdings if h['stk_cd'] == stk_cd), None)
    if not match:
        _log.error(f'[수동매도] {stk_cd} 보유 내역 없음')
        return

    sell_qty = min(qty, match['qty'])
    if sell_qty <= 0:
        _log.error(f'[수동매도] {stk_cd} 매도 가능 수량 0')
        return

    pnl = (match['cur_price'] - match['avg_price']) * sell_qty
    trade_value = match['cur_price'] * sell_qty
    total_asset = summary['total_asset']
    asset_ratio = (trade_value / total_asset) if total_asset > 0 else 0.0
    holding_ratio = sell_qty / match['qty'] if match['qty'] > 0 else 0.0

    result = sell_market(stk_cd, sell_qty, dmst_stex_tp=current_exchange(), env=env)
    if not order_accepted(result):
        _log.error(f'[수동매도-주문거부] {match["stk_nm"]}({stk_cd}) {sell_qty}주 → {result} '
                   f'(거래 이력에 기록하지 않음)')
        return result
    _log.info(f'[수동매도:{env or KIWOOM_ENV}] {match["stk_nm"]}({stk_cd}) 매입가={match["avg_price"]:,.0f}원 '
              f'현재가={match["cur_price"]:,.0f}원 {sell_qty}주 매도, 손익={pnl:+,.0f}원, '
              f'거래대금={trade_value:,.0f}원(자산의 {asset_ratio:.1%}, 보유수량의 {holding_ratio:.0%}) → {result}')
    _record_trade(stk_cd, match['stk_nm'], 'sell', 'manual', sell_qty, match['cur_price'], match['avg_price'], pnl,
                  asset_ratio=asset_ratio, holding_ratio=holding_ratio,
                  ord_no=result.get('ord_no'), env=env)
    return result


def manual_cancel_order(stk_cd: str, ord_no: str, side: str, qty: int = 0,
                        env: Optional[str] = None):
    """미체결 주문 취소(대시보드 '주문 목록'의 취소 버튼).

    side는 주문 목록 응답의 'buy'/'sell'을 그대로 받아 kt10003/kt10004 선택에 쓴다(내부적으로
    '1'/'2'로 변환). qty=0이면 잔량 전부 취소.

    ⚠️ v8이 낸 주문(v8_owned=True)을 취소해도 **v8 자신의 상태(kiwoom_v8_pending*.json)는
    그대로**다. v8은 다음 장중 주기(run_v8_buy_cycle)에서 해당 후보가 여전히 유효하다고
    판단하면 같은 자리에 주문을 다시 낼 수 있다 — 이 함수는 딱 "지금 이 주문"만 취소한다.
    """
    acnt_no, acnt_pwd = get_account_credentials(env)
    if not (acnt_no and acnt_pwd):
        _log.error(f'[수동취소] 계좌 정보 미설정 (env={env or KIWOOM_ENV})')
        return
    api_side = '1' if side == 'buy' else '2'
    result = cancel_order(ord_no, stk_cd, qty, side=api_side,
                          dmst_stex_tp=current_exchange(), env=env)
    if not order_accepted(result):
        _log.error(f'[수동취소-거부] {stk_cd} ord_no={ord_no} qty={qty or "전량"} -> {result}')
        return result
    _log.info(f'[수동취소:{env or KIWOOM_ENV}] {stk_cd} ord_no={ord_no} qty={qty or "전량"} -> {result}')
    return result


if __name__ == '__main__':
    import sys
    if '--token' in sys.argv:
        # 토큰 수동 발급 (KIWOOM_ENV에 맞는 앱키/시크릿으로 발급 후 .env에 자동 저장)
        from auto_trading.kiwoom_api import _refresh_token, KIWOOM_ENV
        _refresh_token()
        print(f'[{KIWOOM_ENV}] 토큰 발급 완료 (.env에 저장됨)')
    elif '--dump' in sys.argv:
        # 모의투자 응답 원본 필드명 확인용
        dump_holdings_raw(ACNT_NO, ACNT_PWD)
    elif '--fills' in sys.argv:
        # 당일 체결내역 조회 (ka10076) — 정산 없이 확인만
        for _f in get_filled_orders(ACNT_NO, ACNT_PWD):
            print(f"{_f['ord_tm']:>8} {_f['ord_no']:>9} {str(_f['stk_nm'])[:10]:<12} {_f['side']:<5} "
                  f"주문{_f['ord_qty']:>4} 체결{_f['cntr_qty']:>4} 미체결{_f['oso_qty']:>3} "
                  f"@{_f['cntr_pric']:>10,.0f} 수수료{_f['cmsn']:>7,.0f} 세금{_f['tax']:>6,.0f}")
    elif '--reconcile' in sys.argv:
        # 당일 거래이력에 실제 체결 데이터 채워넣기. --dry-run이면 통계만.
        _d = None
        if '--date' in sys.argv:
            _d = sys.argv[sys.argv.index('--date') + 1]
        print(reconcile_fills(dry_run='--dry-run' in sys.argv, session_date=_d))
    elif '--transfer' in sys.argv:
        # 계좌 입출금을 손익 기준선에 반영 (입금 양수 / 출금 음수)
        # 사용법: python -m auto_trading.kiwoom_trailing_stop --transfer 259052 [--note "입금"]
        idx = sys.argv.index('--transfer')
        _args = sys.argv[idx + 1:]
        if not _args:
            print('사용법: python -m auto_trading.kiwoom_trailing_stop --transfer <금액> [--note "설명"]')
        else:
            _amt = float(_args[0].replace(',', ''))
            _note = ''
            if '--note' in sys.argv:
                _note = sys.argv[sys.argv.index('--note') + 1]
            _res = record_cash_transfer(_amt, _note)
            print(f'기준선 반영 완료: 일 {_res["daily_start"]:,.0f} / '
                  f'주 {_res["weekly_start"]:,.0f} / 월 {_res["monthly_start"]:,.0f}')
    elif '--buy' in sys.argv:
        # 사용법: python -m auto_trading.kiwoom_trailing_stop --buy <종목코드> [수량]
        # 수량 생략 시 가용 현금 전액으로 시장가 매수
        idx = sys.argv.index('--buy')
        args = sys.argv[idx + 1:]
        if not args:
            print('사용법: python -m auto_trading.kiwoom_trailing_stop --buy <종목코드> [수량]')
        else:
            _stk_cd = args[0]
            _qty = int(args[1]) if len(args) > 1 else None
            manual_buy(_stk_cd, _qty)
    elif '--sell' in sys.argv:
        # 사용법: python -m auto_trading.kiwoom_trailing_stop --sell <종목코드> <수량>
        idx = sys.argv.index('--sell')
        args = sys.argv[idx + 1:]
        if len(args) < 2:
            print('사용법: python -m auto_trading.kiwoom_trailing_stop --sell <종목코드> <수량>')
        else:
            manual_sell(args[0], int(args[1]))
    else:
        if is_market_open():
            run_cycle()
        else:
            print('장 시간이 아님 (평일 09:00~15:30만 동작)')
