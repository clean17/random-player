"""
키움 계좌 보유 종목 트레일링 스탑 자동 매매.

기본 전략 (수정하려면 아래 상수만 변경):
  - 손절            : -6%  → 전량 즉시 청산
  - 목표가          : +10% / +15% / +20% 각 단계 도달 시마다 1/3씩 매도 (단계별 최초 1회만)
  - 트레일링 활성화 : 수익률 +5% 도달 후 고점 추적 시작
  - 트레일링 폭     : 고점 대비 -4%p 이탈 시 그 시점 잔여 수량의 1/3 매도
  - 최소 익절 보호선 : +2% (트레일링 청산선이 +2% 밑으로 내려가지 않도록 고정).
    청산선이 이 보호선에 걸려서 트리거된 경우엔 분할 없이 잔여 수량 전량 청산(추가 하락 방지).
  - 한 종목당 최대 3회(3분할)까지만 매도 — 목표가 단계와 트레일링이 같은 3분할 예산을 공유함.
    트레일링 매도는 "직전 매도 시점의 고점보다 더 높은 새 고점"을 갱신해야만 다시 트리거됨
    (같은 고점에서 반복 매도되는 것 방지).
  - 보유 중 추가 매수로 평단가가 바뀌면 고점/목표가 단계 등 진행상태는 리셋되고 새 평단가 기준으로
    사다리/트레일링을 처음부터 다시 평가함 (rate가 평단가 기준 값이라 예전 %는 더 이상 같은 척도가 아님).
  - 정체 보호: 트레일링 매도가 한 번 나간 뒤 그보다 더 높은 새 고점 없이 가격이 계속 흘러내리면
    트레일링이 재발동되지 않아 잔여 물량이 손절선(-6%)까지 보호 없이 노출될 수 있음. 이를 막기 위해
    그 매도에 쓰인 트리거선(고점-4%p 또는 보호선)보다 추가로 -6%p(STALL_GAP) 더 밀리면 잔여 전량 청산.

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

from job.kiwoom_api import get_holdings_and_summary, sell_market, buy_market, get_current_price, get_current_price_and_name, \
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

    # 서버(run.py)와 CLI(-m job.kiwoom_*)가 같은 파일에 동시에 쓰므로,
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

STOP_LOSS_RATE = -0.06
TARGET_RATES = [0.10, 0.15, 0.20]  # 단계별 목표가, 도달할 때마다 1/3씩 매도
TRAIL_ACTIVATE_RATE = 0.05
TRAIL_GAP = 0.04
MIN_PROFIT_FLOOR = 0.02
STALL_GAP = 0.06  # 정체 보호: 마지막 트레일링 매도 이후 새 고점 없이 그 트리거선보다 추가로 이만큼 더 밀리면 잔여 전량 청산

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
                   asset_ratio: Optional[float] = None, holding_ratio: Optional[float] = None):
    """매수/매도 1건을 거래 이력 파일에 append. 대시보드 이력/기간별 손익 집계에 사용.
    asset_ratio  : 이 거래대금(qty*price)이 총자산에서 차지한 비율 (0.05 = 5%)
    holding_ratio: 매도 시 그 종목 보유수량 대비 이번에 판 비율 (0.33 = 33%). 매수는 None."""
    event = {
        'ts': datetime.datetime.now().isoformat(timespec='seconds'),
        'stk_cd': stk_cd,
        'stk_nm': stk_nm or stk_cd,
        'side': side,       # 'buy' / 'sell'
        'reason': reason,   # 'stop_loss' / 'trailing' / 'target' / 'manual'
        'qty': qty,
        'price': price,
        'avg_price': avg_price,
        'pnl': pnl,
        'asset_ratio': asset_ratio,
        'holding_ratio': holding_ratio,
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
    }


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
        pos_state = _fresh_position_state(qty)
    elif qty < pos_state['remaining_qty']:
        # 수동 매도 등으로 외부에서 수량이 줄어든 경우, 고점/분할 진행 상태는 유지하고 수량만 동기화
        pos_state['remaining_qty'] = qty

    if pos_state['remaining_qty'] <= 0:
        pos_state['exited'] = True
        return pos_state

    # 이전 버전(단일 목표가 target_hit) 상태 파일과의 호환: target_idx가 없으면 마이그레이션
    if 'target_idx' not in pos_state:
        pos_state['target_idx'] = 1 if pos_state.get('target_hit') else 0

    # 1) 손절 — 다른 조건과 무관하게 잔여 수량 전량 즉시 청산
    if rate <= STOP_LOSS_RATE:
        sell_qty = pos_state['remaining_qty']
        pnl = (cur_price - avg_price) * sell_qty
        trade_value = cur_price * sell_qty
        asset_ratio = (trade_value / total_asset) if total_asset > 0 else 0.0
        holding_ratio = 1.0  # 손절은 항상 잔여 전량
        sell_market(stk_cd, sell_qty, dmst_stex_tp=current_exchange())
        _log.info(f'[손절] {stk_nm}({stk_cd}) rate={rate:.2%} 매입가={avg_price:,.0f}원 현재가={cur_price:,.0f}원 '
                  f'{sell_qty}주 전량 청산, 손익={pnl:+,.0f}원, 거래대금={trade_value:,.0f}원(자산의 {asset_ratio:.1%})')
        _record_trade(stk_cd, stk_nm, 'sell', 'stop_loss', sell_qty, cur_price, avg_price, pnl,
                      asset_ratio=asset_ratio, holding_ratio=holding_ratio)
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
    # 트레일링이 (고점-4%p)가 아니라 최소 보호선(+2%)에 걸려서 트리거된 경우 — 더 밀리면 손절선까지
    # 내줄 수 있으므로 분할 매도 대신 잔여 수량 전량을 청산한다.
    trailing_floor_trigger = trailing_trigger and trigger_level <= MIN_PROFIT_FLOOR + 1e-9

    # 3) 목표가(+10/15/20%) — 단계별로 최초 1회씩 트리거 (도달한 가장 높은 단계까지 한 번에 반영)
    target_idx = pos_state['target_idx']
    target_trigger = target_idx < len(TARGET_RATES) and rate >= TARGET_RATES[target_idx]
    target_level = TARGET_RATES[target_idx] if target_trigger else None

    if pos_state['thirds_sold'] < 3 and (trailing_trigger or target_trigger):
        pos_state['thirds_sold'] += 1
        if trailing_floor_trigger:
            # 최소 보호선(+2%)까지 밀린 경우는 분할하지 않고 잔여 수량 전부 청산
            sell_qty = pos_state['remaining_qty']
        else:
            # 마지막(3번째) 트리거는 나눗셈 나머지까지 포함해 잔여 수량 전부 정리
            sell_qty = pos_state['remaining_qty'] if pos_state['thirds_sold'] >= 3 \
                else min(pos_state['tranche_qty'], pos_state['remaining_qty'])

        if sell_qty > 0:
            pnl = (cur_price - avg_price) * sell_qty
            trade_value = cur_price * sell_qty
            asset_ratio = (trade_value / total_asset) if total_asset > 0 else 0.0
            holding_ratio = sell_qty / pos_state['remaining_qty'] if pos_state['remaining_qty'] > 0 else 0.0
            sell_market(stk_cd, sell_qty, dmst_stex_tp=current_exchange())
            if target_trigger:
                reason = f'목표가{target_level:.0%}'
            elif trailing_floor_trigger:
                reason = '트레일링-보호선전량청산'
            else:
                reason = '트레일링'
            _log.info(f'[{reason} {pos_state["thirds_sold"]}/3차] {stk_nm}({stk_cd}) rate={rate:.2%} '
                      f'peak={peak_rate:.2%} 매입가={avg_price:,.0f}원 현재가={cur_price:,.0f}원 '
                      f'{sell_qty}주 매도, 손익={pnl:+,.0f}원, 거래대금={trade_value:,.0f}원'
                      f'(자산의 {asset_ratio:.1%}, 보유수량의 {holding_ratio:.0%}), 잔여 {pos_state["remaining_qty"] - sell_qty}주')
            _record_trade(stk_cd, stk_nm, 'sell', 'target' if target_trigger else 'trailing',
                           sell_qty, cur_price, avg_price, pnl,
                           asset_ratio=asset_ratio, holding_ratio=holding_ratio)
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
                          f'매입가={avg_price:,.0f}원 현재가={cur_price:,.0f}원 {sell_qty}주 전량 청산, '
                          f'손익={pnl:+,.0f}원, 거래대금={trade_value:,.0f}원(자산의 {asset_ratio:.1%})')
                _record_trade(stk_cd, stk_nm, 'sell', 'stall', sell_qty, cur_price, avg_price, pnl,
                              asset_ratio=asset_ratio, holding_ratio=1.0)
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
        f'오늘손익(자산기준)={asset_pnl["daily"]["pnl"]:+,.0f}원({asset_pnl["daily"]["rate"]:+.2%}) '
        f'주간손익(자산기준)={asset_pnl["weekly"]["pnl"]:+,.0f}원({asset_pnl["weekly"]["rate"]:+.2%}) '
        f'월간손익(자산기준)={asset_pnl["monthly"]["pnl"]:+,.0f}원({asset_pnl["monthly"]["rate"]:+.2%}) '
        f'오늘손익(체결기준)={trade_pnl["daily"]["pnl"]:+,.0f}원({trade_pnl["daily"]["rate"]:+.2%}) '
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
        from job.kiwoom_api import _refresh_token, KIWOOM_ENV
        _refresh_token()
        print(f'[{KIWOOM_ENV}] 토큰 발급 완료 (.env에 저장됨)')
    elif '--dump' in sys.argv:
        # 모의투자 응답 원본 필드명 확인용
        dump_holdings_raw(ACNT_NO, ACNT_PWD)
    elif '--buy' in sys.argv:
        # 사용법: python -m job.kiwoom_trailing_stop --buy <종목코드> [수량]
        # 수량 생략 시 가용 현금 전액으로 시장가 매수
        idx = sys.argv.index('--buy')
        args = sys.argv[idx + 1:]
        if not args:
            print('사용법: python -m job.kiwoom_trailing_stop --buy <종목코드> [수량]')
        else:
            _stk_cd = args[0]
            _qty = int(args[1]) if len(args) > 1 else None
            manual_buy(_stk_cd, _qty)
    elif '--sell' in sys.argv:
        # 사용법: python -m job.kiwoom_trailing_stop --sell <종목코드> <수량>
        idx = sys.argv.index('--sell')
        args = sys.argv[idx + 1:]
        if len(args) < 2:
            print('사용법: python -m job.kiwoom_trailing_stop --sell <종목코드> <수량>')
        else:
            manual_sell(args[0], int(args[1]))
    else:
        if is_market_open():
            run_cycle()
        else:
            print('장 시간이 아님 (평일 09:00~15:30만 동작)')
