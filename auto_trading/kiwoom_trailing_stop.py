"""
키움 계좌 보유 종목 트레일링 스탑 자동 매매.

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
실제 평가/매매는 is_market_open() 기준 월~금 아래 세 구간에서만 수행됨:
  - 08:00~08:50 : 넥스트트레이드(NXT) 프리마켓
  - 09:00~15:20 : KRX 정규장
  - 15:30~20:00 : 넥스트트레이드(NXT) 애프터마켓
08:50~09:00(동시호가)과 15:20~15:30(KRX 종가 단일가매매)은 연속체결이 아니라서 제외한다.
주문 시 거래소 구분(dmst_stex_tp)은 current_exchange()로 시간대에 맞게 자동 선택됨
(NXT 세션에선 'NXT', KRX 정규장에선 'KRX'). NXT 미지원 종목은 그 시간대 주문이 거부될 수 있음.
실전 투자 전 반드시 KIWOOM_ENV=mock(모의투자)으로 먼저 검증할 것.
"""
import os
import json
import logging
import logging.handlers
import datetime
from typing import Dict, Optional
from dotenv import load_dotenv, find_dotenv

from auto_trading.kiwoom_api import get_holdings_and_summary, sell_market, buy_market, get_current_price, get_current_price_and_name, \
    dump_holdings_raw, get_account_credentials, get_account_summary
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
    from concurrent_log_handler import ConcurrentTimedRotatingFileHandler
    _file_handler = ConcurrentTimedRotatingFileHandler(
        os.path.join(_LOG_DIR, 'trading.log'), when='midnight', backupCount=180, encoding='utf-8'
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

STATE_FILE = os.path.join(os.path.dirname(__file__), 'kiwoom_trailing_state.json')
TRADES_FILE = os.path.join(_LOG_DIR, 'trades.jsonl')  # 실현손익 이력(승률/손익비 계산용) — 기록 누락 가능성 있음
BASELINE_FILE = os.path.join(_LOG_DIR, 'asset_baseline.json')  # 일/주/월 시작 시점 총자산 스냅샷

# KIWOOM_ENV(mock/real)에 맞는 계좌번호 쌍을 가져옴 — 모의/실전 계좌번호가 다르므로 직접 os.environ으로 읽지 않음
ACNT_NO, ACNT_PWD = get_account_credentials()


# 넥스트트레이드(NXT, 대체거래소) 세션. 종목별 NXT 거래가능 여부는 별도 확인 안 함 — 이 시간대에
# 보유/매매 대상 종목이 NXT 미지원이면 주문이 거부될 수 있음. 정확한 경계는 변경될 수 있으니
# 실거래 전 Kiwoom API 문서로 재확인할 것.
NXT_PREMARKET_START = datetime.time(8, 0)
NXT_PREMARKET_END = datetime.time(8, 50)      # 08:50~09:00은 NXT/KRX 둘 다 세션 없음
NXT_AFTERMARKET_START = datetime.time(15, 30)
NXT_AFTERMARKET_END = datetime.time(20, 0)
KRX_REGULAR_START = datetime.time(9, 0)
KRX_REGULAR_END = datetime.time(15, 20)       # 15:20~15:30은 KRX 종가 단일가매매(연속체결 아님)


def is_market_open() -> bool:
    now = datetime.datetime.now()
    if now.weekday() >= 5:  # 토/일 제외
        return False
    t = now.time()
    if NXT_PREMARKET_START <= t < NXT_PREMARKET_END:
        return True
    if KRX_REGULAR_START <= t < KRX_REGULAR_END:
        return True
    if NXT_AFTERMARKET_START <= t <= NXT_AFTERMARKET_END:
        return True
    return False


def current_exchange() -> str:
    """현재 시각 기준 주문을 넣을 거래소 코드. is_market_open()이 False인 시간대에 호출하면
    의미 없음(호출 전 is_market_open()으로 이미 걸러졌다고 가정)."""
    t = datetime.datetime.now().time()
    if KRX_REGULAR_START <= t < KRX_REGULAR_END:
        return 'KRX'
    return 'NXT'  # 프리마켓(08:00~08:50)/애프터마켓(15:30~20:00)


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


def _record_trade(stk_cd: str, stk_nm: Optional[str], side: str, reason: str,
                   qty: int, price: float, avg_price: float, pnl: float,
                   asset_ratio: Optional[float] = None, holding_ratio: Optional[float] = None,
                   rate: Optional[float] = None, peak_rate: Optional[float] = None,
                   trigger_level: Optional[float] = None, tranche: Optional[str] = None):
    """매수/매도 1건을 거래 이력 파일에 append. 대시보드 이력/기간별 손익 집계에 사용.
    asset_ratio  : 이 거래대금(qty*price)이 총자산에서 차지한 비율 (0.05 = 5%)
    holding_ratio: 매도 시 그 종목 보유수량 대비 이번에 판 비율 (0.33 = 33%). 매수는 None.
    rate         : 매도 시점 수익률(예: -0.05). "작게 여러 번 이기고 크게 한 번 진다"처럼
                   reason만으로는 안 보이는 걸 사후 분석하려면 필요.
    peak_rate    : 이 종목이 보유 중 찍었던 최고 수익률. armed 안 된 채 바로 손절된 건지,
                   한 번 올랐다가 되돌림으로 손절된 건지 구분하는 데 쓴다.
    trigger_level: 이 매도를 발동시킨 청산선(트레일링 트리거가/손절선).
    tranche      : 3분할 중 몇 번째인지 ('1/3'~'3/3'). 트레일링/목표가에만 사용."""
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
        'asset_ratio': asset_ratio,
        'holding_ratio': holding_ratio,
        'rate': rate,
        'peak_rate': peak_rate,
        'trigger_level': trigger_level,
        'tranche': tranche,
    }
    try:
        with open(TRADES_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(event, ensure_ascii=False) + '\n')
    except OSError as e:
        _log.error(f'거래 기록 저장 실패: {e}')


def get_trade_history(limit: int = 200) -> List[Dict]:
    """최근 거래 이력 (최신순)."""
    if not os.path.exists(TRADES_FILE):
        return []
    events = []
    with open(TRADES_FILE, 'r', encoding='utf-8') as f:
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


def _iter_sell_events() -> List[Dict]:
    """trades.jsonl에서 매도(side='sell') 이벤트만 읽어 (날짜 파싱된) dict 리스트로 반환."""
    events = []
    if not os.path.exists(TRADES_FILE):
        return events
    with open(TRADES_FILE, 'r', encoding='utf-8') as f:
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


def get_pnl_summary() -> Dict:
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

    for ev in _iter_sell_events():
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


def get_win_loss_ratio() -> Optional[float]:
    """손익비(Risk-Reward Ratio) = 실현 평균이익 / 실현 평균손실(절대값). 매도 이력 전체 기준.
    손실 거래가 하나도 없으면 None(무한대 취급)."""
    wins = [ev['pnl'] for ev in _iter_sell_events() if ev.get('pnl', 0.0) > 0]
    losses = [-ev['pnl'] for ev in _iter_sell_events() if ev.get('pnl', 0.0) < 0]
    if not losses:
        return None
    if not wins:
        return 0.0
    avg_win = sum(wins) / len(wins)
    avg_loss = sum(losses) / len(losses)
    return avg_win / avg_loss


def _load_baseline() -> Dict:
    if not os.path.exists(BASELINE_FILE):
        return {}
    try:
        with open(BASELINE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_baseline(data: Dict):
    with open(BASELINE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _ensure_baseline(current_total_asset: float) -> Dict:
    """일/주/월이 바뀌면 새 기준선을 기록. 기준선은 '전일 마지막 관측 자산'(사실상 전일 종가 자산)을
    사용한다 — 오늘 첫 조회 시점 자산으로 잡으면 그 전에 발생한 수익/손실이 0으로 묻히기 때문.
    API 오류로 총자산이 0/음수로 들어오면 기준선을 건드리지 않는다."""
    data = _load_baseline()
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
        _save_baseline(data)
    return data


def get_asset_based_pnl(current_total_asset: float) -> Dict:
    """실제 총자산 변동 기준 일/주/월 손익. 거래 누락·수수료·세금과 무관하게 항상 정확함
    (trades.jsonl 기반 get_pnl_summary()의 실현손익 집계는 기록되지 않은 거래가 있으면 틀릴 수 있음)."""
    zero = {'pnl': 0.0, 'rate': 0.0}
    if not current_total_asset or current_total_asset <= 0:
        # API 오류 등으로 총자산이 비정상이면 기준선을 오염시키지 않고 0 반환
        return {'daily': dict(zero), 'weekly': dict(zero), 'monthly': dict(zero)}

    baseline = _ensure_baseline(current_total_asset)

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
    }


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
        sell_qty = pos_state['remaining_qty']
        pnl = (cur_price - avg_price) * sell_qty
        trade_value = cur_price * sell_qty
        asset_ratio = (trade_value / total_asset) if total_asset > 0 else 0.0
        holding_ratio = 1.0  # 손절은 항상 잔여 전량
        label = '되돌림손절' if was_armed else '손절'
        peak_txt = f' 고점={pos_state["peak_rate"]:.2%}' if was_armed else ''
        sell_market(stk_cd, sell_qty, dmst_stex_tp=current_exchange())
        _log.info(f'[{label}] {stk_nm}({stk_cd}) rate={rate:.2%}{peak_txt} (손절선 {stop_level:.1%}) '
                  f'매입가={avg_price:,.0f}원 현재가={cur_price:,.0f}원 '
                  f'{sell_qty}주 전량 청산, 손익={pnl:+,.0f}원, 거래대금={trade_value:,.0f}원(자산의 {asset_ratio:.1%})')
        _record_trade(stk_cd, stk_nm, 'sell', 'giveback_stop' if was_armed else 'stop_loss',
                      sell_qty, cur_price, avg_price, pnl,
                      asset_ratio=asset_ratio, holding_ratio=holding_ratio,
                      rate=rate, peak_rate=pos_state.get('peak_rate'), trigger_level=stop_level)
        pos_state['remaining_qty'] = 0
        pos_state['exited'] = True
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
        floor_full_exit = trailing_floor_trigger and not target_trigger
        if floor_full_exit:
            pos_state['thirds_sold'] = 3
            sell_qty = pos_state['remaining_qty']
        else:
            pos_state['thirds_sold'] += 1
            # 마지막(3번째) 트리거는 나눗셈 나머지까지 포함해 잔여 수량 전부 정리
            sell_qty = pos_state['remaining_qty'] if pos_state['thirds_sold'] >= 3 \
                else min(pos_state['tranche_qty'], pos_state['remaining_qty'])

        if sell_qty > 0:
            pnl = (cur_price - avg_price) * sell_qty
            trade_value = cur_price * sell_qty
            asset_ratio = (trade_value / total_asset) if total_asset > 0 else 0.0
            holding_ratio = sell_qty / pos_state['remaining_qty'] if pos_state['remaining_qty'] > 0 else 0.0
            sell_market(stk_cd, sell_qty, dmst_stex_tp=current_exchange())
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
                      f'(자산의 {asset_ratio:.1%}, 보유수량의 {holding_ratio:.0%}), 잔여 {pos_state["remaining_qty"] - sell_qty}주')
            _record_trade(stk_cd, stk_nm, 'sell', reason_key,
                           sell_qty, cur_price, avg_price, pnl,
                           asset_ratio=asset_ratio, holding_ratio=holding_ratio,
                           rate=rate, peak_rate=peak_rate, trigger_level=trigger_level, tranche=tranche_txt)
            pos_state['remaining_qty'] -= sell_qty

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
                sell_market(stk_cd, sell_qty, dmst_stex_tp=current_exchange())
                _log.info(f'[정체보호전량청산] {stk_nm}({stk_cd}) rate={rate:.2%} 직전고점={pos_state["last_sold_peak"]:.2%} '
                          f'트리거선={trig_used - STALL_GAP:.2%} 매입가={avg_price:,.0f}원 현재가={cur_price:,.0f}원 {sell_qty}주 전량 청산, '
                          f'손익={pnl:+,.0f}원, 거래대금={trade_value:,.0f}원(자산의 {asset_ratio:.1%})')
                _record_trade(stk_cd, stk_nm, 'sell', 'stall', sell_qty, cur_price, avg_price, pnl,
                              asset_ratio=asset_ratio, holding_ratio=1.0,
                              rate=rate, peak_rate=pos_state['last_sold_peak'],
                              trigger_level=trig_used - STALL_GAP)
                pos_state['remaining_qty'] = 0
                pos_state['exited'] = True

    return pos_state


def run_cycle():
    if not (ACNT_NO and ACNT_PWD):
        _log.error('KIWOOM_ACNT_NO / KIWOOM_ACNT_PWD가 .env에 설정되지 않음')
        return

    holdings, summary = get_holdings_and_summary(ACNT_NO, ACNT_PWD)
    if not holdings:
        return
    total_asset = summary['total_asset']

    state = _load_state()
    held_codes = set()

    for holding in holdings:
        stk_cd = holding['stk_cd']
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
        f'\n오늘손익(자산기준)={asset_pnl["daily"]["pnl"]:+,.0f}원({asset_pnl["daily"]["rate"]:+.2%}) '
        f'주간손익(자산기준)={asset_pnl["weekly"]["pnl"]:+,.0f}원({asset_pnl["weekly"]["rate"]:+.2%}) '
        f'월간손익(자산기준)={asset_pnl["monthly"]["pnl"]:+,.0f}원({asset_pnl["monthly"]["rate"]:+.2%}) '
        f'\n오늘손익(체결기준)={trade_pnl["daily"]["pnl"]:+,.0f}원({trade_pnl["daily"]["rate"]:+.2%}) '
        f'주간손익(체결기준)={trade_pnl["weekly"]["pnl"]:+,.0f}원({trade_pnl["weekly"]["rate"]:+.2%}) '
        f'월간손익(체결기준)={trade_pnl["monthly"]["pnl"]:+,.0f}원({trade_pnl["monthly"]["rate"]:+.2%}) '
        f'손익비={ratio_str}'
    )


def manual_buy(stk_cd: str, qty: Optional[int] = None):
    """수동 시장가 매수. qty 생략 시 가용 현금(총자산-보유종목평가금액) 전액으로 매수."""
    if not (ACNT_NO and ACNT_PWD):
        _log.error('KIWOOM_ACNT_NO / KIWOOM_ACNT_PWD가 .env에 설정되지 않음')
        return

    price, stk_nm = get_current_price_and_name(stk_cd)
    if price <= 0:
        _log.error(f'[수동매수] {stk_cd} 현재가 조회 실패')
        return

    s = get_account_summary(ACNT_NO, ACNT_PWD)
    total_asset = s['total_asset']
    if qty is None:
        cash = total_asset - s['tot_evlt_amt']
        qty = int(cash // price)

    if qty <= 0:
        _log.error(f'[수동매수] {stk_nm}({stk_cd}) 현재가={price:,}원, 매수 가능 수량 0')
        return

    trade_value = qty * price
    asset_ratio = (trade_value / total_asset) if total_asset > 0 else 0.0

    result = buy_market(stk_cd, qty, dmst_stex_tp=current_exchange())
    _log.info(f'[수동매수] {stk_nm}({stk_cd}) 현재가={price:,}원 {qty}주 → {result}, '
              f'거래대금={trade_value:,.0f}원(자산의 {asset_ratio:.1%})')
    _record_trade(stk_cd, stk_nm, 'buy', 'manual', qty, price, price, 0.0, asset_ratio=asset_ratio)
    return result


def manual_sell(stk_cd: str, qty: int):
    """수동 시장가 매도. qty는 실제 보유수량으로 자동 제한됨."""
    if not (ACNT_NO and ACNT_PWD):
        _log.error('KIWOOM_ACNT_NO / KIWOOM_ACNT_PWD가 .env에 설정되지 않음')
        return

    holdings, summary = get_holdings_and_summary(ACNT_NO, ACNT_PWD)
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

    result = sell_market(stk_cd, sell_qty, dmst_stex_tp=current_exchange())
    _log.info(f'[수동매도] {match["stk_nm"]}({stk_cd}) 매입가={match["avg_price"]:,.0f}원 '
              f'현재가={match["cur_price"]:,.0f}원 {sell_qty}주 매도, 손익={pnl:+,.0f}원, '
              f'거래대금={trade_value:,.0f}원(자산의 {asset_ratio:.1%}, 보유수량의 {holding_ratio:.0%}) → {result}')
    _record_trade(stk_cd, match['stk_nm'], 'sell', 'manual', sell_qty, match['cur_price'], match['avg_price'], pnl,
                  asset_ratio=asset_ratio, holding_ratio=holding_ratio)
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
