# -*- coding: utf-8 -*-
"""v8 청산 — ATR 샹들리에 + 트레일링 절반 재무장 + 익절 절반 + 최대보유 + 하한선. (Python 3.8)

근거: C:\\my-project\\strategy-ab-backtest\\ANALYSIS_V8.md §1
      2026-09-10 v10 파라미터 전환 근거: 같은 리포의 trail_pct_sweep.py / alloc_sweep_fresh.py /
      hard_floor 그리드서치(당시 대화, 최신 pkl 기준 25슬롯 고정) — 트레일-1.5%/최대보유5일/
      hard_floor-11%/투입10% 조합이 현행(트레일-5%/최대보유10일/hard_floor없음/투입4%) 대비
      CAGR +56.2%→+163.8%, MDD -19.0%→-15.8%, Sharpe 2.27→3.27 (3-fold 전부 양수).
      ⚠️ 5개 파라미터를 동시에 그리드서치로 찾은 값이라 과최적화 위험이 있다는 점을 감안했다
      (인접값들도 비슷하게 좋아 완전한 우연은 아닌 것으로 판단, 근거는 위 스크립트 출력 참고).

  매 주기(30초) 평가 순서
    0) 하한선(hard_floor) -11%    : 현재가 <= 진입가 x 0.89            -> 잔량 전량 (재무장 상태 무관)
    1) ATR(14) x 3.0 샹들리에 손절 : 현재가 <= 진입후최고가 - 3.0*ATR  -> 잔량 전량
    2) 트레일링 -1.5%              : 현재가 <= 최고가 x 0.985          -> 최초수량의 1/2
                                     발동 후 해제, 고점 갱신 시 재무장
    3) 익절 +20%                   : 현재가 >= 진입가 x 1.20           -> 최초수량의 1/2 (1회)
    4) 최대보유 5 거래일            -> 잔량 전량

  장 마감 후 1회 `run_v8_eod()` 로 peak 갱신 + 재무장 판정.

소유권 분리 — 기존 kiwoom_trailing_stop.py 와 동시에 돌아간다.
   v8 이 매수 주문을 낸 종목(kiwoom_v8_strategy.v8_owned_codes())만 이 모듈이 청산하고,
   그 외(v8 전환 전부터 보유했거나 fire 전략이 산 종목)는 기존 트레일링이 담당한다.
   두 모듈이 같은 종목을 서로 다른 규칙으로 파는 사고를 이 분리로 막는다.
"""
import os
import sys
import json
import datetime
import logging
from typing import Dict, Optional

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from auto_trading import kiwoom_api as api          # noqa: E402
from auto_trading import kiwoom_v8_strategy as v8   # noqa: E402
from auto_trading.kiwoom_api import env_path, get_trading_logger  # noqa: E402
from auto_trading.kiwoom_trailing_stop import _record_trade  # noqa: E402

# 2026-08-24: 예전엔 getLogger()만 하고 핸들러를 안 붙여서, 스케줄러(run.py) 경로로 돌 때
# INFO 로그가 전부 사라졌다. 상세는 kiwoom_api.get_trading_logger() docstring 참고.
_log = get_trading_logger('kiwoom_v8_exit')

V8_EXIT_ENABLED = True         # 소유권 분리(v8_owned_codes)로 기존 트레일링과 공존한다

ATR_MULT = 3.0
# 2026-09-10 v10: -5% -> -1.5%. HARD_FLOOR_PCT 라는 절대 안전망이 새로 생겨서, 트레일링을
# 훨씬 타이트하게 잡아 자주·빨리 절반씩 이익실현하고 슬롯 회전을 빠르게 돌리는 쪽이 백테스트상
# 더 낫다(위 모듈 docstring 근거 참고). 단독으로 5%->1.5%만 바꾸면(하한선 없이) 오히려
# 백테스트가 나빠지므로 HARD_FLOOR_PCT 와 반드시 같이 움직여야 한다.
TRAIL_PCT = 0.015
# 2026-08-26 사용자 요청: 트레일링 트리거(peak*(1-TRAIL_PCT))에 처음 닿아도 즉시 팔지 않고
# 이 시간(초)만큼 재확인한다 — 그때도 여전히 트리거 이하일 때만 진짜로 판다(고점에서 살짝
# 밀렸다가 바로 더 오르는 노이즈를 걸러내려는 목적). ⚠️ 분봉 데이터가 없어(strategy-ab-backtest
# 도 일봉만 있음, core.py:114) 백테스트로 검증할 수 없는 값이다 — 라이브/모의 관찰로만 판단.
# 30초로 우선 적용, 관찰 후 1분으로 늘릴지 결정.
TRAIL_CONFIRM_SECONDS = 30
TRAIL_FRAC = 0.5
# 2026-08-27: 개장 후 이 분(分)까지, px가 전일종가와 정확히 같으면 계좌평가 지연으로 보고
# 매매 판단을 보류한다(위 run_v8_exit_cycle 본문 주석 참고). 라이브 관찰 1건 근거라 보수적으로 3분.
STALE_OPEN_GUARD_MIN = 3
TP_PCT = 0.20
TP_FRAC = 0.5
# 2026-09-10 v10: 10 -> 5 거래일. 슬롯 회전(체결건수) 증가가 CAGR 개선의 핵심 메커니즘 —
# 위 모듈 docstring 근거 참고.
# 2026-09-13 v11: 5 -> 7 거래일.
#   ⚠️ 근거 엔진이 바뀌었다. v10까지의 수치는 dailylimit.scan() 의 시간순서 편향(미래에 더 좋은
#   체결이 있으면 이른 체결을 버림 — ANALYSIS_V10.md §2-1, v10_verify_ordering.py 로 독립 재현)
#   위에서 나온 값이라 과대평가였다. 편향 없는 날짜순 스캐너 + ±30% 밴드 + K(동시 대기주문)
#   제약으로 다시 재면:
#       현행 깊이(25%)에서  보유 5일 +2.10% -> 7일 +4.35%  (MDD -18.5%->-16.4%, 3-fold 전부 양수)
#       깊이 40%에서        보유 5일 +15.18% -> 7일 +17.62% (Sharpe 1.21->1.36)
#   **깊이·투입비중과 무관하게 양쪽에서 개선되는 유일한 변경**이라 단독 반영했다.
#   보유 10일도 +16.24%로 5일보다 낫다(4일 +15.17%) — 5~10 구간에서 7 근처가 완만한 정점이고
#   스파이크가 아니다. 근거: strategy-ab-backtest/ANALYSIS_V11.1.md, v11_1_oneat_a_time.py
MAX_HOLD_DAYS = 7
# 2026-09-10 v10 신설 -> 2026-09-11 비활성화(None).
#   도입 근거였던 "하한선이 CAGR/MDD/Sharpe를 모두 개선한다"는 스윕은 **K(동시 대기주문 수)
#   제약을 모델링하지 않은 백테스트**였다. backtest.run_portfolio()는 체결 당일에만 현금을
#   차감하는데, 실계좌는 지정가가 체결될 때까지 최대 10거래일 예수금을 묶는다. 그래서 하한선의
#   이점으로 계산됐던 "포지션 슬롯을 빨리 비워 체결이 는다"가 실제로는 성립하지 않는다 —
#   체결 병목은 포지션 슬롯이 아니라 주문 슬롯(현금)이기 때문이다.
#   alloc_k.py 방식으로 주문잔존을 시뮬레이션해 다시 재면(2026-09-11, 최신 pkl, ALLOC 3~5%)
#   하한선은 모든 조합에서 CAGR을 4~5%p 깎았다:
#     트레일1.5%/보유5일  하한없음 +23.0%  vs  하한-11% +19.1%  (ALLOC 4%)
#     트레일1.5%/보유10일 하한없음 +20.2%  vs  하한-11% +15.2%  (ALLOC 4%)
#   -25% 급락을 받아내는 전략이라 -11%에서 강제 손절하면 되돌림 구간을 잘라먹고, 상방은 이미
#   트레일링 1.5%가 절반을 확보하고 있어 하한선은 비용만 남는다.
#   되살리려면 값을 다시 넣으면 되지만, 반드시 K 제약을 건 백테스트로 재검증할 것.
HARD_FLOOR_PCT = None
ANOMALY_DROP = 0.35            # 직전 관측가 대비 -35% 이상 급락이면 매도하지 않고 정지

# 2026-09-14: 애프터마켓(16:00~20:00) 시장가 매도 거부 대응.
# 실측 로그: 085620/094170/124500/354200 트레일링 매도가 전부
# "[2000](521790:해당 호가유형은 주문 불가능한 시간입니다.)" (return_code 20)로 거부됐다 —
# 이 시간대는 trde_tp='3'(시장가) 자체를 안 받는다(NXT의 옛 제약과 달리 이번엔 KRX 자체
# 애프터마켓인데도 마찬가지). 지정가(trde_tp='0')만 받으므로, 청산 4곳(하한선/ATR샹들리에/
# 트레일링/익절/보유상한 — 아래 _sell() 하나로 통일) 전부 애프터마켓엔 현재가에서
# AFTERMARKET_SELL_SLIPPAGE 만큼 낮춘 공격적 지정가를 쓴다. 완전한 시장가 체감을 흉내내되
# (즉시 체결을 노림) 진짜 시장가처럼 무제한으로 밀리지는 않게 하한을 둔 것 — 정규장에서는
# 지금까지처럼 그대로 시장가를 쓴다(바뀌는 게 없다).
# ⚠️ 값은 추정치다. 분봉 데이터가 없어 애프터마켓 호가창 두께를 백테스트로 검증할 수
# 없다 — 라이브 로그(주문거부 여부, 실제 체결가와의 괴리)로 관찰 후 조정할 것.
AFTERMARKET_SELL_SLIPPAGE = 0.01   # 현재가 대비 -1%

# ⚠️ env_path 필수 (kiwoom_api.env_path docstring 의 2026-08-14 사고 참고).
STATE_PATH = env_path(os.path.join(os.path.dirname(__file__), 'kiwoom_v8_positions.json'))


def log_config():
    """서버(스케줄러) 시작 시 1회 호출 — 지금 이 프로세스에 실제로 로드된 v8 청산 상수를
    로그에 남긴다 (2026-09-15 사용자 요청, kiwoom_v8_strategy.log_config()와 같은 목적).
    ⚠️ 상수를 하나라도 추가/변경하면 이 함수도 같이 갱신할 것."""
    _log.info(
        'v8 청산 설정: V8_EXIT_ENABLED=%s ATR_MULT=%.1f TRAIL_PCT=%.1f%% TRAIL_FRAC=%.0f%% '
        'TRAIL_CONFIRM_SECONDS=%d초 TP_PCT=%.0f%% TP_FRAC=%.0f%% MAX_HOLD_DAYS=%d영업일 '
        'HARD_FLOOR_PCT=%s ANOMALY_DROP=%.0f%% AFTERMARKET_SELL_SLIPPAGE=%.0f%%',
        V8_EXIT_ENABLED, ATR_MULT, TRAIL_PCT * 100, TRAIL_FRAC * 100, TRAIL_CONFIRM_SECONDS,
        TP_PCT * 100, TP_FRAC * 100, MAX_HOLD_DAYS,
        ('%.0f%%' % (HARD_FLOOR_PCT * 100)) if HARD_FLOOR_PCT is not None else 'None(비활성)',
        ANOMALY_DROP * 100, AFTERMARKET_SELL_SLIPPAGE * 100)


def _load() -> Dict:
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            _log.error('상태 로드 실패: %s', e)
    return {}


def _save(st: Dict):
    tmp = STATE_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_PATH)


def _business_days(d0: str) -> int:
    try:
        a = datetime.date.fromisoformat(d0)
    except Exception:
        return 0
    b = datetime.date.today()
    return int(np.busday_count(a, b))


def _init_pos(stk_cd: str, entry: float, qty: int) -> Dict:
    d = v8._load_daily(stk_cd)
    atr = v8._atr14(d) if d is not None else entry * 0.05
    if not np.isfinite(atr) or atr <= 0:
        atr = entry * 0.05
    return {'entry': float(entry), 'atr': float(atr), 'peak': float(entry),
            'shares0': int(qty), 'trail_armed': True, 'last_fire_peak': None,
            'tp_done': False, 'entry_date': datetime.date.today().isoformat(),
            'last_price': float(entry)}


def _sell(stk_cd: str, qty: int, px: float) -> dict:
    """청산 4곳(하한선/ATR샹들리에/트레일링/익절/보유상한)이 공유하는 매도 진입점.

    정규장은 지금까지와 동일하게 시장가. 애프터마켓(16:00~20:00)은 시장가 주문 자체가
    거부되므로(위 AFTERMARKET_SELL_SLIPPAGE 주석의 2026-09-14 실측 참고) 현재가보다
    AFTERMARKET_SELL_SLIPPAGE 만큼 낮춘 지정가로 대신 낸다 — 즉시 체결을 노리는 '공격적
    지정가'다. 호가단위는 kiwoom_v8_strategy의 틱 라운딩을 그대로 쓴다(매수/매도 공용
    로직이라 이름은 '_round_tick'이지만 내림 방향이 매도에도 유리하게 작동한다 — 더 낮은
    지정가일수록 매수 호가와 더 빨리 만난다).
    """
    if not api.is_krx_aftermarket_open():
        return api.sell_market(stk_cd, qty)
    limit_px = v8._round_tick(px * (1.0 - AFTERMARKET_SELL_SLIPPAGE))
    res = api.sell_limit(stk_cd, qty, limit_px)
    _log.info('v8 애프터마켓 지정가매도 %s qty=%d 현재가=%.0f -> 지정가=%d -> %s',
              stk_cd, qty, px, limit_px, res)
    return res


def run_v8_exit_cycle():
    """30초 주기. 보유 종목을 v8 규칙으로 청산."""
    if not V8_EXIT_ENABLED:
        return
    if not v8.is_market_open():      # 시장가 매도 — KRX 정규장 + 2026-09-14 애프터마켓(16:00~20:00)
        return
    acnt_no, acnt_pwd = api.get_account_credentials()
    if not acnt_no or not acnt_pwd:
        return
    holdings = api.get_holdings(acnt_no, acnt_pwd)
    st = _load()
    if not holdings and st and not all(p.get('pending_exit') for p in st.values()):
        # ⚠️ 조회 실패와 '진짜 전량 청산'을 구분할 수 없다. 아래 정리 루프가 상태를 전부
        #    지워버리면 peak / tp_done / trail_armed 기준선이 사라져 재진입 시 오판한다.
        # 단, 남은 포지션 전부가 pending_exit(=이미 매도 주문을 내고 체결 확인만 기다리는
        # 중)이면 얘기가 다르다 — 그건 '마지막 남은 포지션까지 진짜로 다 팔렸다'는 정상
        # 신호일 가능성이 높다(2026-09-14 pending_exit 도입 전엔 소유권을 매도 접수 즉시
        # 놓아서 이 케이스 자체가 안 보였다). 그래서 이때는 스킵하지 않고 계속 진행해
        # 아래 '계좌에서 사라진 종목 정리'가 소유권을 정상적으로 해제하게 한다.
        _log.warning('v8 청산: 보유 목록이 비었는데 상태 %d건이 남아 있다 — '
                     '조회 실패 가능성이 있어 이번 사이클은 건너뛴다', len(st))
        return
    live = set()
    owned = v8.v8_owned_codes()      # v8 이 산 종목만 담당. 나머지는 기존 트레일링 소관.

    for h in holdings:
        code = h.get('stk_cd')
        stk_nm = h.get('stk_nm') or ''   # 2026-09-14: 로그에 코드만 찍혀 종목을 못 알아보기 쉬워 이어붙인다
        qty = int(h.get('qty') or 0)
        if not code or qty <= 0:
            continue
        if code not in owned:
            continue
        # est_fee는 '지금 보유수량 전량(qty)'을 판다고 가정한 수수료+세금 추정 합계다
        # (kt00018 원본 sum_cmsn+tax) — 부분매도(트레일링/익절 1/2씩)엔 수량 비례로 나눠 쓴다.
        # 2026-09-01: kiwoom의 evltv_prft/prft_rt는 이미 이 비용을 뺀 순손익 기준인데
        # 여기 pnl은 가격차만 계산해서 손익이 실제보다 낙관적으로 찍혔다(오킨스전자 등).
        full_qty = qty
        est_fee_total = h.get('est_fee') or 0.0
        live.add(code)
        pos = st.get(code)
        if pos is not None and pos.get('pending_exit'):
            # 2026-09-14: 청산 주문을 냈지만 아직 체결 확인 전이다. 예전엔 주문이 '접수'만
            # 되면 바로 release_ordered() 로 소유권을 놓아버렸는데, 애프터마켓 지정가는
            # 정규장 시장가와 달리 체결까지 몇 분~그 이상 걸릴 수 있다(실사고: 354200,
            # 2026-09-14 19:12 접수 후 10분 넘게 미체결). 그 사이 소유권이 이미 없어져
            # 레거시 트레일링(kiwoom_trailing_stop.py)이 같은 종목을 중복으로 팔려다
            # "매도가능수량 부족"으로 30초마다 계속 거부당하는 레이스가 실제로 발생했다.
            # 그래서 이 종목이 holdings 에서 실제로 사라질 때까지(=체결 확인, 아래 '계좌에서
            # 사라진 종목 정리' 참고) 규칙 재평가를 건너뛰고 소유권도 계속 쥐고 있는다.
            # ⚠️ 한계: 부분체결로 수량만 줄고 잔량이 남아 계속 holdings 에 보이면, 이 종목은
            # 그 잔량에 대해 새 규칙을 평가하지 않고 계속 대기 상태로 남는다 — 중복 주문을
            # 막는 안전한 기본값이지만, 자동으로 재주문/재평가하지는 않는다.
            continue
        if pos is None:
            pos = _init_pos(code, float(h.get('avg_price') or 0) or float(h.get('cur_price') or 0), qty)
            st[code] = pos
            _log.info('v8 포지션 등록 %s(%s) entry=%.0f atr=%.0f qty=%d',
                      code, stk_nm, pos['entry'], pos['atr'], qty)
        elif qty > int(pos.get('shares0') or 0) and not pos.get('tp_done') \
                and pos.get('trail_armed', True):
            # 부분 체결 잔량이 추가로 체결되면 보유수량이 등록 시점보다 늘어난다.
            # shares0 을 갱신하지 않으면 '최초수량의 1/2' 매도가 실제 절반보다 작아진다.
            # 단, 이미 분할 매도가 시작된 뒤에는 갱신하지 않는다(기준이 흔들린다).
            _log.info('v8 추가체결 반영 %s(%s) shares0 %d -> %d', code, stk_nm, pos['shares0'], qty)
            pos['shares0'] = qty
            pos['entry'] = float(h.get('avg_price') or 0) or pos['entry']
        pos['stk_nm'] = stk_nm   # '계좌에서 사라진 종목 정리'(체결확인) 로그가 이름을 쓸 수 있게 매 사이클 갱신

        px = float(h.get('cur_price') or 0)
        if px <= 0:
            continue
        # 개장 직후 전일종가 고착 감지 — 2026-08-27 실측: kt00018(보유종목 실시간평가)이
        # 09:00:20에도 일부 종목은 전일 종가를 그대로 들고 있었다(215790 617=08/26 종가,
        # 08/27 저가 647보다도 낮은 값). 61초 뒤 재확인해도 안 바뀐 채로 트레일링이 발동됨
        # (095행 001770/121850/179900/215790 4/6종목이 정확히 전일종가와 일치, 확인함).
        # ANOMALY_DROP(35%)은 이 정도(9~13%) 괴리는 못 거른다. "개장 후 3분 이내 + 전일종가와
        # 소수점까지 일치"만 좁게 걸러 스킵 — 값이 다르면(진짜 급락 포함) 정상 평가한다.
        now_t = datetime.datetime.now()
        if now_t.hour == 9 and now_t.minute < STALE_OPEN_GUARD_MIN:
            d_chk = v8._load_daily(code)
            prev_close = v8.prev_close_of(d_chk) if d_chk is not None else None
            if prev_close is not None and px == prev_close:
                _log.warning('v8 개장직후 전일종가 고착 의심 %s(%s) px=%.0f(=전일종가) — 이번 사이클 매매판단 보류',
                             code, stk_nm, px)
                continue
        # 이상 감지 — 매도하지 않고 스킵 (액면분할/권리락 방어)
        prev = float(pos.get('last_price') or px)
        if prev > 0 and px / prev - 1.0 <= -ANOMALY_DROP:
            _log.error('v8 이상감지 %s(%s): %.0f -> %.0f (%.1f%%) 매도 보류',
                       code, stk_nm, prev, px, (px / prev - 1) * 100)
            continue
        pos['last_price'] = px

        # ⚠️ peak 을 장중에도 올려야 한다. run_v8_eod 만으로 갱신하면 하루 종일 전일 고가를
        #    쓰게 되고, 그러면 손절선(peak - 3*ATR)과 트레일링선(peak*0.95)이 실제보다 낮아져
        #    매도가 늦게 나간다. 백테스트는 당일 고가를 peak 에 반영한다(entry_day_high='close'
        #    로 진입일만 예외 처리).
        if px > float(pos.get('peak') or 0):
            pos['peak'] = px

        entry, peak, atr = pos['entry'], pos['peak'], pos['atr']
        shares0 = int(pos['shares0'])
        trail_qty = max(1, int(round(shares0 * TRAIL_FRAC)))
        tp_qty = max(1, int(round(shares0 * TP_FRAC)))

        # 0) 하한선(hard_floor) — 진입가 대비 절대 하한. 재무장 상태·ATR 폭과 무관하게 전량 정리.
        #    ATR 샹들리에보다 먼저 평가한다 — ATR이 넓은 종목은 샹들리에(peak-3*ATR)가 이 하한선
        #    보다 한참 아래에 있어 하한선이 더 먼저(=덜 손해 보고) 걸러줘야 의미가 있다.
        #    ⚠️ HARD_FLOOR_PCT=None 이면 이 규칙 자체를 건너뛴다(2026-09-11 비활성화, 위 상수 주석 참고).
        floor_px = entry * (1.0 + HARD_FLOOR_PCT) if HARD_FLOOR_PCT is not None else None
        if floor_px is not None and px <= floor_px:
            res = _sell(code, qty, px)
            ok = isinstance(res, dict) and str(res.get('return_code', '')) == '0'
            if not ok:
                _log.warning('v8 하한선(hard_floor) 주문 거부 %s(%s) qty=%d px=%.0f floor=%.0f -> %s',
                             code, stk_nm, qty, px, floor_px, res)
                continue
            v8.mark_sold(code)
            _log.info('v8 하한선(hard_floor) %s(%s) qty=%d px=%.0f floor=%.0f(entry%.0f%%) -> %s',
                      code, stk_nm, qty, px, floor_px, HARD_FLOOR_PCT * 100, res)
            fee_share = est_fee_total * (qty / full_qty) if full_qty > 0 else 0.0
            pnl = (px - entry) * qty - fee_share
            _record_trade(code, h.get('stk_nm'), 'sell', 'v8_hard_floor', qty, px, entry, pnl,
                          holding_ratio=1.0, rate=px / entry - 1.0, peak_rate=peak / entry - 1.0,
                          trigger_level=floor_px / entry - 1.0, ord_no=res.get('ord_no'))
            # 소유권 해제는 체결 확인 후로 미룬다(위 pending_exit 주석 참고) — 여기서 바로
            # release_ordered 하지 않는다.
            pos['pending_exit'] = True
            continue

        # 1) ATR 샹들리에 손절 — 전량
        stop_px = peak - ATR_MULT * atr
        if px <= stop_px:
            res = _sell(code, qty, px)
            ok = isinstance(res, dict) and str(res.get('return_code', '')) == '0'
            if not ok:
                # 주문이 거부되면(예: 사용자가 직전에 수동으로 이미 전량 매도해 잔량이 없음)
                # 실제로 판 게 없으니 거래이력에 기록하지도, 포지션 상태를 지우지도 않는다 —
                # 2026-08-31 121850 사고: 이 체크가 없어 수동매도와 v8손절이 같은 체결을
                # 중복으로 거래이력에 남겨 당일 수익이 실제의 약 2배로 잡혔다.
                _log.warning('v8 손절(ATR샹들리에) 주문 거부 %s(%s) qty=%d px=%.0f stop=%.0f -> %s',
                             code, stk_nm, qty, px, stop_px, res)
                continue
            v8.mark_sold(code)
            _log.info('v8 손절(ATR샹들리에) %s(%s) qty=%d px=%.0f stop=%.0f -> %s',
                      code, stk_nm, qty, px, stop_px, res)
            fee_share = est_fee_total * (qty / full_qty) if full_qty > 0 else 0.0
            pnl = (px - entry) * qty - fee_share
            _record_trade(code, h.get('stk_nm'), 'sell', 'v8_atr_stop', qty, px, entry, pnl,
                          holding_ratio=1.0, rate=px / entry - 1.0, peak_rate=peak / entry - 1.0,
                          trigger_level=stop_px / entry - 1.0, ord_no=res.get('ord_no'))
            pos['pending_exit'] = True   # 소유권 해제는 체결 확인 후로 미룬다(위 pending_exit 주석 참고)
            continue

        # 2) 트레일링(TRAIL_PCT) — 최초수량의 1/2. TRAIL_CONFIRM_SECONDS 재확인(위 상수 설명 참고).
        trail_trigger = peak * (1.0 - TRAIL_PCT)
        if pos.get('trail_armed') and px <= trail_trigger:
            now = datetime.datetime.now()
            since_dt = None
            since_raw = pos.get('trail_watch_since')
            if since_raw:
                try:
                    since_dt = datetime.datetime.fromisoformat(since_raw)
                except ValueError:
                    since_dt = None
            if since_dt is not None and since_dt.date() != now.date():
                # kiwoom_trailing_stop.py의 stop_watch_since와 동일한 사고(2026-09-01 103140) —
                # 어제 관찰이 장 마감까지 안 끝나면 밤새 지난 시간이 재확인 시간으로 잡혀
                # 오늘 첫 사이클에 대기 없이 바로 팔린다. 날짜가 바뀌면 관찰을 새로 시작한다.
                since_dt = None
            if since_dt is None:
                pos['trail_watch_since'] = now.isoformat()
                _log.info('v8 트레일링관찰 %s(%s) px=%.0f peak=%.0f trigger=%.0f — %d초 재확인 대기',
                          code, stk_nm, px, peak, trail_trigger, TRAIL_CONFIRM_SECONDS)
            elif (now - since_dt).total_seconds() >= TRAIL_CONFIRM_SECONDS:
                sell_qty = min(trail_qty, qty)
                if sell_qty >= 1:
                    res = _sell(code, sell_qty, px)
                    ok = isinstance(res, dict) and str(res.get('return_code', '')) == '0'
                    if not ok:
                        # 거부 시 trail_watch_since를 건드리지 않아 다음 사이클에 재시도한다.
                        _log.warning('v8 트레일링 주문 거부 %s(%s) qty=%d px=%.0f peak=%.0f -> %s',
                                     code, stk_nm, sell_qty, px, peak, res)
                    else:
                        v8.mark_sold(code)
                        _log.info('v8 트레일링 %s(%s) qty=%d px=%.0f peak=%.0f -> %s',
                                  code, stk_nm, sell_qty, px, peak, res)
                        fee_share = est_fee_total * (sell_qty / full_qty) if full_qty > 0 else 0.0
                        pnl = (px - entry) * sell_qty - fee_share
                        _record_trade(code, h.get('stk_nm'), 'sell', 'v8_trailing', sell_qty, px, entry, pnl,
                                      holding_ratio=sell_qty / qty, rate=px / entry - 1.0,
                                      peak_rate=peak / entry - 1.0, trigger_level=trail_trigger / entry - 1.0,
                                      tranche='1/2', ord_no=res.get('ord_no'))
                        pos['trail_armed'] = False
                        pos['last_fire_peak'] = peak
                        pos['trail_watch_since'] = None
                        qty -= sell_qty
                        if qty <= 0:
                            pos['pending_exit'] = True   # 소유권 해제는 체결 확인 후로 미룬다
                            continue
        elif pos.get('trail_watch_since') is not None:
            _log.info('v8 트레일링관찰해제 %s(%s) px=%.0f 로 회복', code, stk_nm, px)
            pos['trail_watch_since'] = None

        # 3) 익절 +20% — 최초수량의 1/2, 1회
        tp_trigger = entry * (1.0 + TP_PCT)
        if (not pos.get('tp_done')) and px >= tp_trigger:
            sell_qty = min(tp_qty, qty)
            if sell_qty >= 1:
                res = _sell(code, sell_qty, px)
                ok = isinstance(res, dict) and str(res.get('return_code', '')) == '0'
                if not ok:
                    _log.warning('v8 익절 주문 거부 %s(%s) qty=%d px=%.0f (+%.0f%%) -> %s',
                                 code, stk_nm, sell_qty, px, TP_PCT * 100, res)
                else:
                    v8.mark_sold(code)
                    _log.info('v8 익절 %s(%s) qty=%d px=%.0f (+%.0f%%) -> %s',
                              code, stk_nm, sell_qty, px, TP_PCT * 100, res)
                    fee_share = est_fee_total * (sell_qty / full_qty) if full_qty > 0 else 0.0
                    pnl = (px - entry) * sell_qty - fee_share
                    _record_trade(code, h.get('stk_nm'), 'sell', 'v8_take_profit', sell_qty, px, entry, pnl,
                                  holding_ratio=sell_qty / qty, rate=px / entry - 1.0,
                                  peak_rate=peak / entry - 1.0, trigger_level=tp_trigger / entry - 1.0,
                                  tranche='1/2', ord_no=res.get('ord_no'))
                    pos['tp_done'] = True
                    qty -= sell_qty
                    if qty <= 0:
                        pos['pending_exit'] = True   # 소유권 해제는 체결 확인 후로 미룬다
                        continue

        # 4) 최대 보유일
        if _business_days(pos.get('entry_date', '')) >= MAX_HOLD_DAYS:
            res = _sell(code, qty, px)
            ok = isinstance(res, dict) and str(res.get('return_code', '')) == '0'
            if not ok:
                _log.warning('v8 보유상한(%d영업일) 주문 거부 %s(%s) qty=%d -> %s',
                             MAX_HOLD_DAYS, code, stk_nm, qty, res)
                continue
            v8.mark_sold(code)
            _log.info('v8 보유상한(%d영업일) %s(%s) qty=%d -> %s', MAX_HOLD_DAYS, code, stk_nm, qty, res)
            fee_share = est_fee_total * (qty / full_qty) if full_qty > 0 else 0.0
            pnl = (px - entry) * qty - fee_share
            _record_trade(code, h.get('stk_nm'), 'sell', 'v8_max_hold', qty, px, entry, pnl,
                          holding_ratio=1.0, rate=px / entry - 1.0, peak_rate=peak / entry - 1.0,
                          ord_no=res.get('ord_no'))
            pos['pending_exit'] = True   # 소유권 해제는 체결 확인 후로 미룬다(위 pending_exit 주석 참고)
            continue

    # 계좌에서 사라진 종목 정리
    # 2026-09-14: pending_exit(위 주석) 종목은 여기서 실제 체결을 확인한다 — holdings 에서
    # 사라졌다는 것 자체가 '이제 진짜로 다 팔렸다'는 확인이다. 그때 비로소 소유권을 놓는다.
    # pending_exit 이 아닌데도 holdings 에서 사라진 경우(조회 이상 등)는 예전처럼 그냥 지운다
    # — release_ordered 를 안 불렀다는 건 애초에 소유권을 쥔 적이 없다는 뜻이라 안전하다.
    for code in list(st):
        if code in live:
            continue
        pos = st[code]
        if pos.get('pending_exit'):
            _log.info('v8 청산 체결확인 %s(%s) — 소유권 해제', code, pos.get('stk_nm') or '')
            v8.release_ordered(code, quiet=True)   # 위에서 이미 로그를 남겼으니 중복 방지
        st.pop(code, None)
    _save(st)


def run_v8_eod():
    """장 마감 후 1회 — 당일 고가로 peak 갱신 + 재무장 판정."""
    if not V8_EXIT_ENABLED:
        return
    st = _load()
    for code, pos in st.items():
        d = v8._load_daily(code)
        if d is None or len(d) == 0:
            continue
        hi = float(d['high'].iloc[-1])
        if hi > pos['peak']:
            pos['peak'] = hi
        lfp = pos.get('last_fire_peak')
        if (not pos.get('trail_armed')) and lfp is not None and pos['peak'] > float(lfp):
            pos['trail_armed'] = True
            _log.info('v8 트레일링 재무장 %s peak=%.0f > %.0f', code, pos['peak'], lfp)

        # ── 분석용 일별 포지션 스냅샷 (2026-09-04 추가) ───────────────────────
        # 청산이 발동한 건은 trades.jsonl 에 rate/peak_rate/trigger_level 까지 남지만,
        # **발동하지 않고 흘러간 날들**은 아무 데도 안 남아서 "어느 경로로 그 결말에
        # 도달했나"를 재구성할 수 없었다. 30초 사이클마다 남기면 하루 25종목 x 780회로
        # 과하니, 하루 1회(마감 후) 확정값으로만 남긴다.
        try:
            entry = float(pos.get('entry') or 0)
            close = float(d['close'].iloc[-1])
            atr = float(pos.get('atr') or 0)
            api.log_event('v8_signals', {
                'kind': 'position_eod', 'code': code,
                'entry': entry, 'close': close, 'peak': pos.get('peak'), 'atr': atr,
                'rate': (close / entry - 1.0) if entry > 0 else None,
                'peak_rate': (float(pos['peak']) / entry - 1.0) if entry > 0 and pos.get('peak') else None,
                'chandelier': (float(pos['peak']) - ATR_MULT * atr) if pos.get('peak') else None,
                'trail_trigger': (float(pos['peak']) * (1.0 - TRAIL_PCT)) if pos.get('peak') else None,
                'trail_armed': pos.get('trail_armed'), 'tp_done': pos.get('tp_done'),
                'last_fire_peak': pos.get('last_fire_peak'), 'shares0': pos.get('shares0'),
                'entry_date': pos.get('entry_date'),
            })
        except Exception:
            pass
    _save(st)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    if len(sys.argv) > 1 and sys.argv[1] == 'eod':
        run_v8_eod()
    else:
        run_v8_exit_cycle()
    print(json.dumps(_load(), ensure_ascii=False, indent=1))
