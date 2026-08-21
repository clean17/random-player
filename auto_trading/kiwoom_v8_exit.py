# -*- coding: utf-8 -*-
"""v8 청산 — ATR 샹들리에 + 트레일링 절반 재무장 + 익절 절반 + 최대보유. (Python 3.8)

근거: C:\\my-project\\strategy-ab-backtest\\ANALYSIS_V8.md §1

  매 주기(30초) 평가 순서
    1) ATR(14) x 3.0 샹들리에 손절 : 현재가 <= 진입후최고가 - 3.0*ATR  -> 잔량 전량
    2) 트레일링 -5%                : 현재가 <= 최고가 x 0.95           -> 최초수량의 1/2
                                     발동 후 해제, 고점 갱신 시 재무장
    3) 익절 +20%                   : 현재가 >= 진입가 x 1.20           -> 최초수량의 1/2 (1회)
    4) 최대보유 10 거래일           -> 잔량 전량

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
from auto_trading.kiwoom_api import env_path       # noqa: E402

_log = logging.getLogger('kiwoom_v8_exit')

V8_EXIT_ENABLED = True         # 소유권 분리(v8_owned_codes)로 기존 트레일링과 공존한다

ATR_MULT = 3.0
TRAIL_PCT = 0.05
TRAIL_FRAC = 0.5
TP_PCT = 0.20
TP_FRAC = 0.5
MAX_HOLD_DAYS = 10
ANOMALY_DROP = 0.35            # 직전 관측가 대비 -35% 이상 급락이면 매도하지 않고 정지

# ⚠️ env_path 필수 (kiwoom_api.env_path docstring 의 2026-08-14 사고 참고).
STATE_PATH = env_path(os.path.join(os.path.dirname(__file__), 'kiwoom_v8_positions.json'))


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


def run_v8_exit_cycle():
    """30초 주기. 보유 종목을 v8 규칙으로 청산."""
    if not V8_EXIT_ENABLED:
        return
    if not v8.is_market_open():      # 시장가 매도 — KRX 정규장에서만
        return
    acnt_no, acnt_pwd = api.get_account_credentials()
    if not acnt_no or not acnt_pwd:
        return
    holdings = api.get_holdings(acnt_no, acnt_pwd)
    st = _load()
    if not holdings and st:
        # ⚠️ 조회 실패와 '진짜 전량 청산'을 구분할 수 없다. 아래 정리 루프가 상태를 전부
        #    지워버리면 peak / tp_done / trail_armed 기준선이 사라져 재진입 시 오판한다.
        _log.warning('v8 청산: 보유 목록이 비었는데 상태 %d건이 남아 있다 — '
                     '조회 실패 가능성이 있어 이번 사이클은 건너뛴다', len(st))
        return
    live = set()
    owned = v8.v8_owned_codes()      # v8 이 산 종목만 담당. 나머지는 기존 트레일링 소관.

    for h in holdings:
        code = h.get('stk_cd')
        qty = int(h.get('qty') or 0)
        if not code or qty <= 0:
            continue
        if code not in owned:
            continue
        live.add(code)
        pos = st.get(code)
        if pos is None:
            pos = _init_pos(code, float(h.get('avg_price') or 0) or float(h.get('cur_price') or 0), qty)
            st[code] = pos
            _log.info('v8 포지션 등록 %s entry=%.0f atr=%.0f qty=%d',
                      code, pos['entry'], pos['atr'], qty)
        elif qty > int(pos.get('shares0') or 0) and not pos.get('tp_done') \
                and pos.get('trail_armed', True):
            # 부분 체결 잔량이 추가로 체결되면 보유수량이 등록 시점보다 늘어난다.
            # shares0 을 갱신하지 않으면 '최초수량의 1/2' 매도가 실제 절반보다 작아진다.
            # 단, 이미 분할 매도가 시작된 뒤에는 갱신하지 않는다(기준이 흔들린다).
            _log.info('v8 추가체결 반영 %s shares0 %d -> %d', code, pos['shares0'], qty)
            pos['shares0'] = qty
            pos['entry'] = float(h.get('avg_price') or 0) or pos['entry']

        px = float(h.get('cur_price') or 0)
        if px <= 0:
            continue
        # 이상 감지 — 매도하지 않고 스킵 (액면분할/권리락 방어)
        prev = float(pos.get('last_price') or px)
        if prev > 0 and px / prev - 1.0 <= -ANOMALY_DROP:
            _log.error('v8 이상감지 %s: %.0f -> %.0f (%.1f%%) 매도 보류',
                       code, prev, px, (px / prev - 1) * 100)
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

        # 1) ATR 샹들리에 손절 — 전량
        stop_px = peak - ATR_MULT * atr
        if px <= stop_px:
            res = api.sell_market(code, qty)
            v8.mark_sold(code)
            _log.info('v8 손절(ATR샹들리에) %s qty=%d px=%.0f stop=%.0f -> %s',
                      code, qty, px, stop_px, res)
            st.pop(code, None)
            v8.release_ordered(code)
            continue

        # 2) 트레일링 -5% — 최초수량의 1/2
        if pos.get('trail_armed') and px <= peak * (1.0 - TRAIL_PCT):
            sell_qty = min(trail_qty, qty)
            if sell_qty >= 1:
                res = api.sell_market(code, sell_qty)
                v8.mark_sold(code)
                _log.info('v8 트레일링 %s qty=%d px=%.0f peak=%.0f -> %s',
                          code, sell_qty, px, peak, res)
                pos['trail_armed'] = False
                pos['last_fire_peak'] = peak
                qty -= sell_qty
                if qty <= 0:
                    st.pop(code, None)
                    v8.release_ordered(code)
                    continue

        # 3) 익절 +20% — 최초수량의 1/2, 1회
        if (not pos.get('tp_done')) and px >= entry * (1.0 + TP_PCT):
            sell_qty = min(tp_qty, qty)
            if sell_qty >= 1:
                res = api.sell_market(code, sell_qty)
                v8.mark_sold(code)
                _log.info('v8 익절 %s qty=%d px=%.0f (+%.0f%%) -> %s',
                          code, sell_qty, px, TP_PCT * 100, res)
                pos['tp_done'] = True
                qty -= sell_qty
                if qty <= 0:
                    st.pop(code, None)
                    v8.release_ordered(code)
                    continue

        # 4) 최대 보유일
        if _business_days(pos.get('entry_date', '')) >= MAX_HOLD_DAYS:
            res = api.sell_market(code, qty)
            v8.mark_sold(code)
            _log.info('v8 보유상한(%d영업일) %s qty=%d -> %s', MAX_HOLD_DAYS, code, qty, res)
            st.pop(code, None)
            v8.release_ordered(code)
            continue

    # 계좌에서 사라진 종목 정리
    for code in list(st):
        if code not in live:
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
    _save(st)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    if len(sys.argv) > 1 and sys.argv[1] == 'eod':
        run_v8_eod()
    else:
        run_v8_exit_cycle()
    print(json.dumps(_load(), ensure_ascii=False, indent=1))
