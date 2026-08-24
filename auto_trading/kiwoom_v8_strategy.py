# -*- coding: utf-8 -*-
"""v8 전략 — 매일 스크리닝 + 매일 갱신 지정가 매수. (Python 3.8)

근거: C:\\my-project\\strategy-ab-backtest\\ANALYSIS_V8.md
  기간 2023-07-17~2026-08-18 (3.09년), 500만원 기준
  거래 n=3,817 기대 +2.80% (t=17.25) / 포트 CAGR +115.2% MDD -28.1% Sharpe 2.24
  3 fold 전부 양수 (F1 +122% / F2 +143% / F3 +84%)

전략 요약
  [스크리닝] 매일 15:55 (pkl 15:50 갱신분 = 확정 종가 이후)
      · 최근 20일 안에 '5일 상승률 +10% 이상' 이력   ← 한 번 힘을 보여준 종목
      · 당일 거래대금 >= 10억, 종가 >= 700원
      · 지정가 = 당일 종가 x 0.70 (-30%), 유효 10 거래일
  [매수] 장중, 도달 가능한 후보에 실제 지정가 주문을 걸어둔다
      · 슬롯 25 / 1회 투입 = 평가자산의 8%
      · 동시 주문 = min(MAX_OPEN_ORDERS, 남은슬롯, 예수금 / 1회투입금)
      · 주문 자리 배분 순위 = gap(오늘 필요한 하락폭 작은 순) > 점수(동순위 판정)
      · 시그널마다 독립 지정가. 주문은 대기 중 최고가에 걸고 체결되면 그 이상은 소진
  [매도] kiwoom_v8_exit.py 참고

⚠️ 기존 fire 전략(15:18 시장가 추격)과 방향이 정반대다. 둘을 같이 켜지 말 것.
   2026-08-19 전환으로 batch_runner 의 kiwoom_fire_buy 잡을 주석 처리했다.
✔ 지정가 주문(trde_tp='0')은 2026-08-19 실계좌에서 접수/취소 확인됨(주문번호 0274100).
  단 하한가보다 낮은 가격은 `[2000] 주문단가가 하한가보다 낮습니다` 로 거부된다.
⚠️ 실계좌 체결까지 간 이력은 아직 없다. 체결률·슬리피지는 미실측이다.
"""
import os
import sys
import json
import glob
import time
import datetime
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from auto_trading import kiwoom_api as api  # noqa: E402
from auto_trading.kiwoom_api import env_path, get_trading_logger  # noqa: E402
from auto_trading.kiwoom_trailing_stop import _record_trade  # noqa: E402

# 2026-08-24: 예전엔 getLogger()만 하고 핸들러를 안 붙여서, 스케줄러(run.py) 경로로 돌 때
# INFO 로그가 전부 사라졌다(가동 후 5일간 trading.log에 v8 관련 줄 0건). 상세는
# kiwoom_api.get_trading_logger() docstring 참고.
_log = get_trading_logger('kiwoom_v8')

_last_regap_ts = 0.0   # 마지막으로 현재가를 조회해 live_gap 을 다시 세운 시각

# ── 안전 스위치 ──────────────────────────────────────────────────────────────
# 실계좌(KIWOOM_ENV=real)에서 돈다. 2026-08-19 전환 완료.
# 되돌리려면 False + batch_runner 의 kiwoom_fire_buy 주석 해제 + 프로세스 재시작.
V8_ENABLED = True

# ── 파라미터 (ANALYSIS_V8.md §1) ─────────────────────────────────────────────
RUN_MIN = 0.10          # 최근 20일 내 5일 상승률 문턱
RUN_LOOKBACK = 20       # 급등 이력 탐색 구간(거래일)
DEPTH = 0.30            # 지정가 = 종가 x (1-DEPTH)
VALID_DAYS = 10         # 지정가 유효기간(거래일)
AMOUNT_MIN = 1_000_000_000   # 당일 거래대금 10억
PRICE_MIN = 700

SLOTS = 25              # 동시 보유 상한
ALLOC = 0.08            # 1회 투입 = 평가자산의 8%
                        #  2026-08-19 측정: 투입액을 줄이면 같은 예수금으로 미체결 주문을
                        #  더 걸 수 있고(K ~= 1/ALLOC), CAGR 은 거의 전부 K 로 결정된다.
                        #    10% K=10  CAGR +28.8%  MDD -35.4%  Sh 0.98  F1 +1%
                        #     8% K=12  CAGR +29.2%  MDD -30.5%  Sh 1.07  F1 +7%  <- 채택
                        #  6.25% K=16  CAGR +28.5%  MDD -30.8%  Sh 1.16
                        #     4% K=25  CAGR +22.0%  MDD -22.6%  Sh 1.26
                        #   2.5% K=40  CAGR +16.5%  MDD -16.6%  Sh 1.41
                        #  더 낮추면 CAGR 을 Sharpe 와 교환한다. 8% 가 CAGR 최대이면서
                        #  Sharpe>1 + 3 fold 전부 양수를 만족한다.
                        #  분석: strategy-ab-backtest/alloc_k.py
MIN_ORDER = 100_000     # 최소 주문금액
CLAMP_TO_BAND = False   # 지정가가 오늘 하한가보다 낮을 때: False=스킵(백테스트 충실), True=하한가로 상향

# ── 감시/주문 정책 ───────────────────────────────────────────────────────────
# 백테스트는 '그날 저가가 지정가에 닿으면 체결'이다. 실매매에서 이걸 재현하는 유일한 방법은
# **실제 지정가 주문을 호가창에 걸어두는 것**이다. 전략의 엣지가 '순간 급락의 꼬리'에 있어서
# 폴링으로 감지한 뒤 주문하는 방식으로는 잡히지 않는다 (아래 측정).
#
# 다만 미체결 주문이 예수금을 묶으므로 동시에 걸 수 있는 수 K 가 제한되고,
# **CAGR 은 거의 전부 K 로 결정된다** (2026-08-19, 원본 파이프라인 + K 제약):
#     K=10  CAGR  +28.9%   K=25  +46.1%   K=100  +81.2%   무제한(861) +114.0%
# K 를 늘리는 유일한 수단은 1회 투입액을 줄이는 것이다 -> ALLOC 주석 참고.
#
# ⚠️ 폴링(감지 후 주문)은 측정으로 폐기했다.  CAGR -41.0%  Sharpe -3.0
#    폴링이 확실히 잡는 것은 '종가까지 지정가 아래에 머문 종목'인데 그게 최악의 거래이고,
#    놓치는 '닿고 반등'(체결 기회의 54.3%, 반등폭 중앙값 +2.9%)이 좋은 거래다.
#    즉 폴링의 포착은 역선택된다. 같은 이유로 LIVE_REGAP(장중 재정렬)도 끈다.
#    분석: strategy-ab-backtest/polling_floor.py
#
# 순서
#   1) [아침 1회, API 0회] pkl 로 오늘 도달 가능한 후보만 남긴다.
#      지정가 < 오늘 하한가(전일종가 x 0.70)면 주문이 거부되므로 제외.
#   2) [아침 1회] gap = 지정가/전일종가 - 1 큰 순(= 오늘 필요한 하락폭이 작은 순).
#      점수는 gap 이 GAP_TIE_BUCKET 이내인 것들의 동순위 판정에만 쓴다.
#      ⚠️ 건당 기대수익만 보면 gap 작은 쪽이 좋지만(+2.34% vs -0.62%), CAGR 은 체결
#         '횟수'에도 좌우되어 gap 큰 순이 압도적으로 낫다. 순서를 뒤집지 말 것.
WATCH_PRIORITY = 'gap'  # 'gap' = 체결 가능성 우선(기본) / 'score' = 백테스트 랭킹 우선
GAP_TIE_BUCKET = 0.02   # gap 을 2%p 단위로 묶어 같은 버킷 안에서만 점수로 순서를 가른다
GAP_PREFILTER = 72      # WATCH_PRIORITY='score' 일 때 점수를 매길 gap 상위 후보 수
MAX_OPEN_ORDERS = 12    # 동시에 걸어둘 미체결 지정가 주문 수 상한(증거금 보호)
LIVE_REGAP = False      # ⚠️ 켜지 말 것. 2026-08-19 측정으로 폐기.
                        #  장중 현재가로 순위를 다시 세우면 '이미 지정가 아래로 내려가
                        #  머물러 있는' 종목 쪽으로 주문을 옮기게 되는데, 그게 가장 나쁜
                        #  거래다. 아래 폴링 측정 참고.
LIVE_REGAP_TOP = 60     # 현재가를 조회할 후보 수. 60 x 0.143초 = 약 8.6초
LIVE_REGAP_EVERY_SEC = 300   # 재조회 주기(초). 아래 실측 근거로 5분.
REGAP_MARGIN = 0.03     # 미주문 후보가 주문중인 것보다 이만큼 더 가까울 때만 교체한다
                        #  (취소는 호가 대기순번을 잃으므로 함부로 바꾸지 않는다)
# ── 폴링 주기 근거 (2026-08-19 실측, 최근 250 거래일 / 시그널 160,762건) ─────
# 체결 기회 6,546건을 '닿은 그 날의 종가'로 분류하면:
#   종가도 지정가 이하 (지속)   2,989건  45.7%   ← 몇 분에 한 번 봐도 잡힌다
#   닿고 반등 (종가 > 지정가)   3,557건  54.3%   ← 반등폭 중앙값 +2.9%
#
# 즉 절반 이상은 '닿았다'를 감지한 뒤 주문을 넣으면 이미 지정가 위로 올라가 있다.
# 폴링으로 쫓아가는 방식은 이 54%를 구조적으로 놓친다 — **호가창에 미리 걸어두는 것이
# 본질이고 폴링은 보조**다. 그래서 폴링을 촘촘히 하는 것보다 '아침에 어디에 걸까'가 중요하다.
#
# 체결일 시가 기준으로 지정가까지 남은 거리:
#   시가에 이미 지정가 이하 11.8% / -3% 이내 26.3% / -5% 이내 42.1% / -10% 이내 75.3%
# 체결의 75%가 '시가부터 이미 -10% 안쪽'인 날에 일어난다. 그래서 개장 직후 시가로 한 번
# 다시 세우는 것이 가장 값어치가 크고(첫 사이클에 무조건 수행), 그 뒤로는 5분이면 충분하다.
#
# 더 짧게 잡으면 교체가 잦아져 오히려 손해다. 교체는 취소를 수반하고, 취소되는 그 주문이
# 바로 위 54%를 잡아주는 장치다. REGAP_MARGIN 3%p 문턱도 같은 이유다.
RESIZE_TOL = 0.20       # 미체결 주문 수량이 '지금 자금 기준 목표'와 이만큼 어긋나면 취소 후 재주문
# (POLL_TOP_N 은 LIVE_REGAP 으로 대체됨 — 단순 감지 로그가 아니라 주문 대상 선정에 쓴다)

PKL_DIR = r'C:\my-project\AutoSales.py\data\pickle'
# ⚠️ env_path 필수. 붙이지 않으면 모의계좌 상태가 실전 매매를 조종한다
#    (kiwoom_api.env_path docstring: 2026-08-14 실전 전환 당일 실제 사고).
STATE_PATH = env_path(os.path.join(os.path.dirname(__file__), 'kiwoom_v8_pending.json'))

# 백테스트와 같은 유니버스. 코드 패턴만으로는 SPAC/ETF/ETN 을 걸러낼 수 없다
# (build_universe.py 는 **종목명**으로 '스팩'/ETF·ETN 브랜드를 제외한다).
# 2026-08-19 확인: 코드 패턴만 쓰면 2,688종목이 통과해 백테스트 유니버스(2,631)에 없는
# 81종목이 섞이고, 실제로 대기 후보에 5건(448760·448830·451700·466910·478780)이 들어와 있었다.
# 신규 상장이 늘면 갱신 필요: strategy-ab-backtest/build_universe.py 실행 후 이 파일을 덮어쓴다.
UNIVERSE_PATH = os.path.join(os.path.dirname(__file__), 'v8_universe.json')

COLMAP = {'시가': 'open', '고가': 'high', '저가': 'low', '종가': 'close', '거래량': 'volume'}

_UNIVERSE = None


def universe_codes() -> Optional[set]:
    """백테스트와 동일한 종목 집합. 파일이 없으면 None (코드 패턴으로 폴백)."""
    global _UNIVERSE
    if _UNIVERSE is None:
        try:
            with open(UNIVERSE_PATH, 'r', encoding='utf-8') as f:
                _UNIVERSE = set(u['code'] for u in json.load(f))
            _log.info('v8 유니버스 %d종목 로드', len(_UNIVERSE))
        except Exception as e:
            _log.error('v8 유니버스 로드 실패 (%s) — 코드 패턴으로 폴백. '
                       'SPAC/ETF/ETN 이 섞일 수 있다.', e)
            _UNIVERSE = set()
    return _UNIVERSE or None

# ── 장 시간 가드 ─────────────────────────────────────────────────────────────
# KRX 정규장만 주문한다. 15:20~15:30 은 종가 단일가라 지정가가 그대로 체결되지 않고,
# NXT 시간대(08:00~08:50, 15:30~20:00)는 kiwoom_trailing_stop 주석대로 거부된다
# (real: 407022). 가드가 없으면 60초마다 거부 로그만 쌓인다.
KRX_OPEN = datetime.time(9, 0)
KRX_CLOSE = datetime.time(15, 20)


def is_market_open() -> bool:
    now = datetime.datetime.now()
    if now.weekday() >= 5:
        return False
    return KRX_OPEN <= now.time() < KRX_CLOSE


# ── 상태 ─────────────────────────────────────────────────────────────────────
def _load_pending() -> Dict:
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            _log.error('pending 로드 실패: %s', e)
    return {'pending': {}, 'ordered': {}, 'updated': None}


def _save_pending(state: Dict):
    tmp = STATE_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_PATH)


# ── 소유권 원장 ──────────────────────────────────────────────────────────────
# v8 과 기존 청산(kiwoom_trailing_stop)이 같은 계좌를 공유한다. 어느 쪽 규칙으로 팔지는
# **누가 산 종목인가**로 가른다. v8 이 주문을 낸 종목만 v8 규칙(ATR 샹들리에 등)으로 청산하고,
# 그 전부터 들고 있던 종목은 기존 규칙(손절 -6% + 보유 5일) 그대로 둔다.
#   · v8 주문 접수 시  -> ordered 원장에 등록
#   · v8 이 전량 청산  -> 원장에서 제거
#   · 보유도 미체결도 아닌 채 ORDER_LEDGER_TTL 일 지나면 자동 정리(체결 안 된 주문)
ORDER_LEDGER_TTL = 30


def _migrate(v: Dict) -> Dict:
    """구 형식(종목당 지정가 1개) -> 신 형식(지정가 목록)으로 변환.

    백테스트(dailylimit.scan)는 **시그널 날마다 별도 지정가**를 만들고 각자 자기 10 거래일
    창을 갖는다. 여러 개가 동시에 대기하고 먼저 닿는 것(=가장 높은 것)에서 체결된다.
    종목당 하나만 들고 유효기간을 연장하던 방식은 대기가 85일까지 늘어나
    -4% 수준의 나쁜 거래를 만들었다(2026-08-19 측정, V8_SWITCHOVER.md 8절).
    """
    if 'limits' in v:
        return v
    v = dict(v)
    v['limits'] = [{'limit': int(v.get('limit') or 0),
                    'age': int(v.get('age') or 0),
                    'sig_date': v.get('sig_date'),
                    'sig_close': v.get('sig_close')}]
    v.pop('limit', None)
    v.pop('age', None)
    return v


def active_limit(v: Dict) -> Optional[int]:
    """대기 중인 지정가 중 **가장 높은 것**. 먼저 닿는 = 먼저 체결되는 가격이다."""
    lims = [int(e['limit']) for e in (v.get('limits') or []) if int(e.get('limit') or 0) > 0]
    return max(lims) if lims else None


def consume_limits(code: str, fill_px: float):
    """체결됨 -> 그 가격 이상의 지정가는 소진 처리. 더 낮은 것은 계속 대기한다.

    백테스트의 `taken` 규칙과 같다: 같은 날 여러 지정가가 닿아도 진입은 1건이고,
    더 낮은 지정가는 이후(포지션 청산 후) 다시 체결 대상이 된다.
    """
    st = _load_pending()
    v = st.get('pending', {}).get(code)
    if not v:
        return
    v = _migrate(v)
    before = len(v['limits'])
    v['limits'] = [e for e in v['limits'] if int(e['limit']) < fill_px]
    if not v['limits']:
        st['pending'].pop(code, None)
    else:
        st['pending'][code] = v
    if before != len(v['limits']):
        st.pop('day', None)          # 오늘자 캐시 무효화
        _save_pending(st)
        _log.info('v8 지정가 소진 %s @%.0f (%d -> %d개)', code, fill_px, before, len(v['limits']))


def sold_today_codes() -> set:
    """오늘 v8 이 매도한 종목. 백테스트 `sequential_filter` 의 '당일 매도 종목 당일 매수 금지'.

    이 규칙이 있어야 scan 전체(기대 +1.90%)에서 채택 집합(+2.80%)으로 걸러진다.
    청산 직후 같은 종목을 다시 받으면 하락이 이어지는 구간을 중복으로 물게 된다.
    """
    st = _load_pending()
    today = datetime.date.today().isoformat()
    return set(c for c, d in (st.get('sold') or {}).items() if d == today)


def mark_sold(code: str):
    """v8 청산이 매도할 때마다 호출 — 당일 재매수 금지 등록."""
    st = _load_pending()
    sold = st.setdefault('sold', {})
    today = datetime.date.today().isoformat()
    # 지난 기록 정리
    for c in list(sold):
        if sold[c] != today:
            del sold[c]
    if sold.get(code) != today:
        sold[code] = today
        _save_pending(st)


def v8_owned_codes() -> set:
    """v8 이 매수 주문을 낸 종목코드. 기존 청산 로직은 이 집합을 건드리지 않아야 한다."""
    return set((_load_pending().get('ordered') or {}).keys())


def _mark_ordered(code: str):
    st = _load_pending()
    od = st.setdefault('ordered', {})
    if code not in od:
        od[code] = datetime.date.today().isoformat()
        _save_pending(st)
        _log.info('v8 소유권 등록 %s', code)


def release_ordered(code: str):
    """v8 이 해당 종목을 완전히 청산했을 때 호출 — 소유권 해제."""
    st = _load_pending()
    od = st.setdefault('ordered', {})
    fq = st.setdefault('filled_qty', {})
    changed = od.pop(code, None) is not None
    if fq.pop(code, None) is not None:
        changed = True
    if changed:
        _save_pending(st)
        _log.info('v8 소유권 해제 %s', code)


def _take_fill_delta(code: str, cur_qty: int) -> int:
    """직전 사이클 대비 늘어난 보유수량. 체결 감지 시 _record_trade 중복 기록을 막는 데 쓴다.

    2026-08-24: v8 은 지금까지 _record_trade 를 한 번도 호출하지 않아 실거래 이력이
    전부 누락됐다(trades_real.jsonl 에 v8 매수 0건). 이 함수는 보유수량 증가분만큼만
    1회 기록하도록 보장한다 — 같은 종목을 같은 사이클(30초)마다 반복 조회해도
    이미 반영된 수량은 delta=0 이라 중복 기록되지 않는다.
    """
    st = _load_pending()
    fq = st.setdefault('filled_qty', {})
    prev = int(fq.get(code, 0))
    delta = cur_qty - prev
    if delta != 0:
        fq[code] = cur_qty
        _save_pending(st)
    return delta


# ── 일봉 ─────────────────────────────────────────────────────────────────────
def _load_daily(code: str) -> Optional[pd.DataFrame]:
    path = os.path.join(PKL_DIR, code + '.pkl')
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_pickle(path)
    except Exception:
        return None
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    if not isinstance(df.index, pd.DatetimeIndex):
        try:
            df.index = pd.to_datetime(df.index)
        except Exception:
            return None
    df = df.rename(columns=COLMAP)
    need = ['open', 'high', 'low', 'close', 'volume']
    if any(c not in df.columns for c in need):
        return None
    try:
        df = df[need].astype('float64')
    except Exception:
        return None
    df = df[~df.index.duplicated(keep='last')].sort_index()
    ok = (df['open'] > 0) & (df['high'] > 0) & (df['low'] > 0) & (df['close'] > 0)
    df = df[ok & df[need].notna().all(axis=1)]
    return df if len(df) >= 80 else None


def _atr14(d: pd.DataFrame) -> float:
    h, l, pc = d['high'], d['low'], d['close'].shift(1)
    tr = pd.concat([(h - l).abs(), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    v = tr.ewm(alpha=1 / 14.0, min_periods=14, adjust=False).mean().iloc[-1]
    return float(v) if np.isfinite(v) else float('nan')


# 거래정지 이력 검사 구간. RUN_LOOKBACK(20)의 rolling(20)이 최대 25행 전(shift(5)+rolling(20))까지
# 보고, ATR(14)도 14행이 필요하다 — 그 구간에 거래정지(거래량 0)가 하나라도 섞이면 5일수익률·
# MA20·ATR이 전부 오염된다. 여유를 조금 더 둬서 25로 잡는다.
HALT_CHECK_WINDOW = 25


def _recently_halted(d: pd.DataFrame, i: int, window: int = HALT_CHECK_WINDOW) -> bool:
    """i번째 행 기준 최근 window거래일 안에 거래정지(거래량=0)가 있었는지.

    2026-08-24 추가 — 183300 실사고 대응. 이 종목은 16거래일 거래정지 후 재개일에
      1) 정지 중 얼어붙은 가격과 비교해 '5일수익률 +27%'라는 가짜 신호가 발생했고
      2) 정지 전(가격 재조정 전) 저장된 낡은 지정가가 재조정 후 가격과 뒤섞여
         gap=+30%라는 말이 안 되는 값으로 최우선 순위에 올라갔다.
    두 문제 다 '최근 거래일이 실제 가격 변동을 담보하지 않는다'는 같은 원인이라,
    신호 생성(screen_today)과 매일 재계산(_features_now) 양쪽에서 이 검사로 막는다.
    score 같은 순위 지표로는 못 거른다 — 실측(2026-08-24)으로 정지 이력이 있는 종목의
    score가 0.01~1.99 전 구간에 흩어져 있어 상관이 없었다.
    """
    lo = max(0, i - window + 1)
    return bool((d['volume'].iloc[lo:i + 1] <= 0).any())


# 데이터 최신성 검사 문턱. 실계좌 pkl 갱신은 09-15시 :10/:30/:50 이라 정상 종목은 항상
# 오늘이나 어제 행이 있다. 연휴가 겹쳐도 5일이면 충분한 여유다.
STALE_MAX_DAYS = 5


def _data_stale(d: pd.DataFrame, max_days: int = STALE_MAX_DAYS) -> bool:
    """마지막 행이 오늘로부터 max_days 이상 지났는지.

    2026-08-24 추가 — 183300 대응으로 만든 _recently_halted() 만으로는 부족했다.
    일부 종목(175250 등)은 정지 구간을 거래량=0 이 아니라 **시가/고가/저가=0** 으로
    표시하는데, 이는 _load_daily() 의 가격>0 필터에 걸려 그 구간의 행 자체가 통째로
    사라진다. 그 결과 남은 마지막 유효 행이 1년 전(175250: 2025-08-05)까지 밀려도
    len(dd)>=21 은 가볍게 넘겨 정상 종목처럼 통과했다. 거래량 검사로는 애초에 안 보이는
    행이라 window 를 늘려도 못 잡는다 — '마지막 행이 언제냐' 자체를 봐야 한다.
    """
    if d is None or len(d) == 0:
        return True
    return (datetime.date.today() - d.index[-1].date()).days > max_days


def _tick(price: float) -> int:
    for bound, t in ((2000, 1), (5000, 5), (20000, 10), (50000, 50),
                     (200000, 100), (500000, 500)):
        if price < bound:
            return t
    return 1000


def _round_tick(price: float) -> int:
    t = _tick(price)
    return int(np.floor(price / t) * t)   # 매수 지정가는 내림(더 유리)


def _ceil_tick(price: float) -> int:
    t = _tick(price)
    return int(np.ceil(price / t) * t)


def prev_close_of(d: pd.DataFrame) -> Optional[float]:
    """전일(오늘 이전 마지막 거래일) 종가.

    ⚠️ pkl 의 마지막 행은 **장중이면 오늘 진행중 데이터**다(2026-08-19 확인:
       005930 마지막 행이 당일 251,000, 전일은 268,500). 하한가 계산에 오늘 값을
       쓰면 실제보다 낮게 나와 `주문단가가 하한가보다 낮습니다` 로 거부된다.
    """
    if d is None or len(d) < 2:
        return None
    today = pd.Timestamp(datetime.date.today())
    idx = d.index
    prev = idx[idx < today]
    if len(prev) == 0:
        return float(d['close'].iloc[-2])
    return float(d['close'].loc[prev[-1]])


def lower_limit_price(prev_close: float) -> int:
    """일일 가격제한폭 하한가(전일 종가 -30%). 호가단위 올림."""
    return _ceil_tick(prev_close * 0.70)


def upper_limit_price(prev_close: float) -> int:
    """일일 가격제한폭 상한가(전일 종가 +30%). 호가단위 내림."""
    return _round_tick(prev_close * 1.30)


def clamp_to_band(limit: int, prev_close: float) -> Optional[int]:
    """주문가를 오늘 하한가 이상으로 올린다.

    ⚠️ 2026-08-19 실계좌 확인: 하한가보다 낮은 지정가는
       `[2000](571552:주문단가가 하한가보다 낮습니다.)` 로 거부된다.
       v8 지정가는 시그널일 종가 -30% 라서, 시그널 후 주가가 더 빠지면
       오늘 하한가 밑으로 내려가 그대로는 주문이 나가지 않는다.
       기본은 **스킵**이다(CLAMP_TO_BAND=False). 하한가로 올려 사면 백테스트에 없던
       더 비싼 진입이 생기기 때문 — 백테스트는 그 날 저가가 지정가에 닿아야만 체결로 본다.
    """
    lo = lower_limit_price(prev_close)
    if limit < lo:
        return lo if CLAMP_TO_BAND else None
    # 반대쪽 — 시그널 후 -46% 이상 폭락하면 지정가가 오늘 상한가보다 높아지고
    # `주문단가가 상한가보다 높습니다` 로 거부된다. 이때는 상한가로 낮춰 낸다.
    # 지정가보다 싼 시장가에 즉시 체결되므로 전략 의도('지정가 이하에서 매수')에 부합한다.
    # 백테스트도 체결가를 min(지정가, 시가)로 잡는다.
    # 빈도: 2026-08-19 측정으로 대기 종목-일 637,215건 중 2건(0.0%).
    hi = upper_limit_price(prev_close)
    if limit > hi:
        return int(hi)
    return int(limit)


# ── 스크리닝 ─────────────────────────────────────────────────────────────────
def screen_today() -> List[Dict]:
    """오늘 종가 기준 신규 후보. 장 마감 후(pkl 확정 뒤) 실행."""
    out = []
    uni = universe_codes()
    for path in glob.glob(os.path.join(PKL_DIR, '*.pkl')):
        code = os.path.splitext(os.path.basename(path))[0]
        if uni is not None:
            if code not in uni:
                continue
        # 폴백: 6자리 전부 숫자 + 끝자리 0 (우선주 코드만 걸러진다. SPAC/ETF/ETN 은 못 걸러냄)
        elif len(code) != 6 or not code.isdigit() or code[-1] != '0':
            continue
        d = _load_daily(code)
        if d is None:
            continue
        if _data_stale(d):
            continue   # 마지막 유효 행이 너무 오래됨 (정지 구간이 가격=0으로 지워진 경우 포함)
        if _recently_halted(d, len(d) - 1):
            continue   # 최근 거래정지 이력 — 5일수익률/MA20/ATR이 얼어붙은 가격으로 오염됨
        c = d['close']
        close = float(c.iloc[-1])
        amount = close * float(d['volume'].iloc[-1])
        if close < PRICE_MIN or amount < AMOUNT_MIN:
            continue
        r5 = c / c.shift(5) - 1.0
        if not (r5.tail(RUN_LOOKBACK).max() >= RUN_MIN):
            continue
        atr = _atr14(d)
        ma20 = float(c.rolling(20).mean().iloc[-1])
        if not np.isfinite(atr) or not np.isfinite(ma20) or ma20 <= 0:
            continue
        limit = _round_tick(close * (1.0 - DEPTH))
        if limit <= 0:
            continue
        out.append({
            'code': code, 'sig_date': str(d.index[-1].date()),
            'sig_close': close, 'limit': limit, 'atr': atr, 'ma20': ma20,
            'prev_close': float(c.iloc[-1]),   # 하한가 계산 기준(스크리닝 시점 종가)
            'amount': amount,
            'drop5': float(close / c.iloc[-6] - 1.0) if len(c) > 6 else 0.0,
        })
    return out


def run_v8_screen() -> Dict:
    """장 마감 후 1회. 신규 후보 추가 + 만료 제거."""
    state = _load_pending()
    pend = state.get('pending', {})
    today = datetime.date.today().isoformat()

    # ⚠️ age 는 '스크리닝 실행 횟수'로 거래일을 근사한다. 그래서 같은 날 두 번 실행되면
    #    (프로세스 재시작 후 잡 재실행, 또는 `python -m ... screen` 수동 실행)
    #    유효기간이 하루가 아니라 이틀씩 깎여 후보가 조기 만료된다.
    #    2026-08-19 실제로 수동 실행 때문에 이중 카운트가 발생했다.
    age_today = (state.get('aged_on') != today)
    if not age_today:
        _log.info('v8 스크리닝: 오늘(%s) 이미 age 를 올렸음 — 만료 카운트는 건너뜀', today)

    # 만료 제거
    #  + 보통주 필터 위반분 청소: screen_today 가 필터를 갖기 전에 저장된 신형우선주
    #    (0004V0, 0082N0 처럼 영문이 섞인 코드)가 남아 있을 수 있다.
    uni = universe_codes()
    for code in list(pend):
        bad = (code not in uni) if uni is not None else               (not (len(code) == 6 and code.isdigit() and code[-1] == '0'))
        if bad:
            _log.info('v8 대기 청소: 유니버스 밖 %s', code)
            del pend[code]
            continue
        v = _migrate(pend[code])
        if age_today:
            for e in v['limits']:
                e['age'] = e.get('age', 0) + 1
        v['limits'] = [e for e in v['limits'] if e.get('age', 0) <= VALID_DAYS]
        if not v['limits']:
            del pend[code]
        else:
            pend[code] = v

    # ── 시그널마다 **독립된 지정가**를 추가한다 (백테스트 dailylimit.scan 과 동일).
    #
    # 각 지정가는 자기 시그널일로부터 10 거래일 창을 갖고, 여러 개가 동시에 대기한다.
    # 주문은 그 중 가장 높은 것(먼저 닿는 것)에 걸고, 체결되면 그 가격 이상은 소진한다.
    #
    # 2026-08-19 측정 (원본 파이프라인 + 동시주문수 제약, 500만원/25슬롯/1회10%):
    #   동시 주문 K=10  CAGR +28.9%  MDD -35.4%  Sharpe 0.99
    #   동시 주문 K=25  CAGR +46.1%  MDD -39.9%  Sharpe 1.29
    #   동시 주문 무제한 CAGR +114.0% MDD -34.0%  Sharpe 2.26   ← 문서 수치(재현 확인)
    # 즉 CAGR 은 거의 전부 '동시에 걸 수 있는 주문 수'로 결정된다.
    #
    # 종목당 지정가 1개만 들고 유효기간을 연장하던 방식은 대기가 85일까지 늘어나
    # -4% 수준의 나쁜 거래 758건을 만들었다. 분석: strategy-ab-backtest/live_v2.py
    added = 0
    for s in screen_today():
        code = s['code']
        lim = int(s['limit'])
        cur = _migrate(pend[code]) if code in pend else None
        entry = {'limit': lim, 'age': 0,
                 'sig_date': s['sig_date'], 'sig_close': s['sig_close']}
        if cur is None:
            s = dict(s)
            s.pop('limit', None)
            s['limits'] = [entry]
            pend[code] = s
            added += 1
        else:
            # 같은 지정가가 이미 있으면 더 최근(age 작은) 것으로 갱신만 한다
            same = [e for e in cur['limits'] if int(e['limit']) == lim]
            if same:
                for e in same:
                    e['age'] = 0
            else:
                cur['limits'].append(entry)
                added += 1
            # 랭킹 재료·ATR 은 최신 시그널 값으로 갱신
            for k in ('atr', 'ma20', 'amount', 'drop5', 'sig_close', 'sig_date'):
                if k in s:
                    cur[k] = s[k]
            if len(cur['limits']) > VALID_DAYS + 2:
                cur['limits'] = sorted(cur['limits'], key=lambda e: e.get('age', 0))[:VALID_DAYS + 2]
            pend[code] = cur
    # 체결되지 않고 방치된 원장 정리 (보유/미체결이 아닌 항목)
    od = state.setdefault('ordered', {})
    for code in list(od):
        try:
            age = (datetime.date.today() - datetime.date.fromisoformat(od[code])).days
        except Exception:
            age = ORDER_LEDGER_TTL + 1
        if age > ORDER_LEDGER_TTL:
            del od[code]

    state['pending'] = pend
    state['updated'] = today
    if age_today:
        state['aged_on'] = today
    # 스크리닝으로 후보가 바뀌었으니 오늘자 캐시를 버린다 -> 다음 장 시작 때 다시 계산
    state.pop('day', None)
    _save_pending(state)
    _log.info('v8 스크리닝: 신규/갱신 %d건, 대기 총 %d건', added, len(pend))
    return state


# ── 매수 ─────────────────────────────────────────────────────────────────────
def buy_limit(stk_cd: str, qty: int, price: int, dmst_stex_tp: str = 'KRX') -> dict:
    """지정가 매수. trde_tp='0' (보통).

    2026-08-19 실계좌에서 접수/취소 확인됨(주문번호 0274100). 체결까지 간 이력은 아직 없다.
    하한가보다 낮은 가격은 `[2000] 주문단가가 하한가보다 낮습니다` 로 거부된다.
    """
    return api.place_order(stk_cd, qty, int(price), side='1', trde_tp='0',
                           dmst_stex_tp=dmst_stex_tp)


def _rank(cands: List[Dict]) -> List[Dict]:
    """pct_rank(-5일수익률) + pct_rank(-(지정가/20일이평)) 높은 순.

    drop5 는 이름과 달리 부호 있는 5일 수익률이다(음수 = 하락). 더 많이 떨어진 쪽을
    높게 매긴다. 이 score 는 **정렬에만** 쓰이고, WATCH_PRIORITY='gap' 인 동안은
    같은 gap 버킷 안의 동순위 판정에만 관여한다.
    """
    if not cands:
        return []
    df = pd.DataFrame([{'drop5': c.get('drop5', 0.0),
                        'px_ma20': c.get('px_ma20', 1.0)}
                       for c in cands])
    sc = (-df['drop5']).rank(pct=True).fillna(0.5).values \
        + (-df['px_ma20']).rank(pct=True).fillna(0.5).values
    for c, v in zip(cands, sc):
        c['score'] = float(v)
    return sorted(cands, key=lambda x: -x['score'])


def _features_now(code: str, v: Dict) -> Optional[Dict]:
    """후보 1건의 특징을 '가장 최근 확정 일봉' 기준으로 다시 계산. pkl 만 읽는다(API 0회).

    지정가(limit)는 시그널일 종가 x 0.70 으로 고정이고 여기서 바꾸지 않는다.
    바뀌는 것은 랭킹 재료(drop5 / ma20 / atr)와 오늘의 도달 가능성(gap)이다.

    ⚠️ 장중 pkl 마지막 행은 오늘 진행중 데이터라 `index < today` 로 잘라낸다.
    """
    d = _load_daily(code)
    if d is None:
        return None
    dd = d[d.index < pd.Timestamp(datetime.date.today())]
    if len(dd) < 21:
        return None
    if _data_stale(dd):
        return None   # 마지막 유효 행이 너무 오래됨 (정지 구간이 가격=0으로 지워진 경우 포함)
    if _recently_halted(dd, len(dd) - 1):
        # 최근 거래정지 이력 — 이 종목의 지정가/랭킹 재료를 오늘 신뢰할 수 없다.
        # (2026-08-24 183300 사고: 정지 전 가격 기준으로 저장된 낡은 지정가가
        #  재조정된 현재가와 뒤섞여 gap이 말이 안 되는 값으로 나왔다.)
        return None
    c = dd['close']
    pc = float(c.iloc[-1])
    if pc <= 0:
        return None
    v = _migrate(v)
    lim = active_limit(v)
    if not lim:
        return None
    ord_px = clamp_to_band(int(lim), pc)
    if ord_px is None or ord_px <= 0:
        return None

    ma20 = float(c.rolling(20).mean().iloc[-1])
    atr = _atr14(dd)
    r = dict(v)
    r['code'] = code
    r['limit'] = int(lim)          # 오늘 주문에 쓸 지정가 (대기 중 최고가)
    r['prev_close'] = pc
    r['ord_px'] = int(ord_px)
    # gap = 오늘 지정가에 닿으려면 전일 종가 대비 몇 % 더 빠져야 하는가 (음수).
    #  ⚠️ '현재가와의 거리'가 아니다. 전일 종가 기준이므로 장중에는 값이 변하지 않는다.
    #     -30%면 오늘 하한가까지 가야 체결, -9%면 -9%만 빠져도 체결.
    r['gap'] = float(ord_px) / pc - 1.0
    r['drop5'] = float(c.iloc[-1] / c.iloc[-6] - 1.0)
    r['ma20'] = ma20 if np.isfinite(ma20) and ma20 > 0 else float(v.get('ma20') or pc)
    r['atr'] = atr if np.isfinite(atr) and atr > 0 else float(v.get('atr') or pc * 0.05)
    r['px_ma20'] = float(ord_px) / max(1.0, r['ma20'])
    return r


def daily_candidates(force: bool = False) -> List[Dict]:
    """오늘 주문 가능한 후보 목록. **하루 1회만 계산하고 캐시**한다.

    gap 과 랭킹 재료는 모두 전일 확정 종가 기준이라 장중에 변하지 않는다.
    그런데 예전 구현은 60초 사이클마다 pkl 731개를 다시 읽어 같은 값을 재계산했다
    (2.25초 x 하루 378사이클 = 849초). 하루 1회로 줄이고 결과를 상태파일에 남긴다.

    동시에 백테스트와의 어긋남 하나를 없앤다 — 랭킹 재료(drop5/ma20)를 시그널일에
    얼려두면 체결까지 며칠 걸린 후보는 낡은 값으로 순위가 매겨진다. 백테스트는
    체결 시점 값으로 순위를 매겼다. 매일 아침 다시 계산하면 그 차이가 하루로 줄어든다.
    """
    st = _load_pending()
    today = datetime.date.today().isoformat()
    day = st.get('day') or {}
    if not force and day.get('date') == today and isinstance(day.get('cands'), list):
        return day['cands']

    pend = st.get('pending') or {}
    out = []
    for code, v in pend.items():
        r = _features_now(code, v)
        if r is not None:
            out.append(r)
    out = _rank(out)
    st['day'] = {'date': today, 'cands': out}
    _save_pending(st)
    _log.info('v8 아침 재계산: 대기 %d건 -> 오늘 주문가능 %d건 (drop5/ma20/atr/gap 갱신)',
              len(pend), len(out))
    return out


def run_v8_buy_cycle():
    """장중 주기 실행.

    ① pkl 로 도달 가능한 후보만 추림 (API 0회)
    ② gap(오늘 필요한 하락폭) 순 정렬 -> LIVE_REGAP_EVERY_SEC 마다 현재가로 live_gap 재정렬
    ③ 자금 한도만큼 **실제 지정가 주문을 호가창에 걸어둔다**
    ④ 후보에서 빠진 주문은 취소, 부분 체결 잔량은 유지, 자금 변동분은 수량 재조정
    """
    if not V8_ENABLED:
        return
    if not is_market_open():
        return
    acnt_no, acnt_pwd = api.get_account_credentials()
    if not acnt_no or not acnt_pwd:
        _log.error('계좌 정보 없음')
        return

    holdings, summary = api.get_holdings_and_summary(acnt_no, acnt_pwd)
    held = {h['stk_cd'] for h in holdings}
    equity = float(summary.get('total_asset') or 0.0)
    # ⚠️ _parse_summary 에는 'cash' 키가 없다. 예수금 = 추정예탁자산 - 보유종목 평가금액.
    cash = max(0.0, equity - float(summary.get('tot_evlt_amt') or 0.0))
    if equity <= 0:
        _log.error('평가자산 조회 실패 — 매수 스킵')
        return

    try:
        unfilled = api.get_unfilled_orders(acnt_no, acnt_pwd)
    except Exception as e:
        _log.error('미체결 조회 실패: %s', e)
        return
    open_buy = {u['stk_cd']: u for u in unfilled
                if '매수' in str(u.get('io_tp_nm', '')) and int(u.get('oso_qty') or 0) > 0}
    _ordered_codes = v8_owned_codes()

    # 체결 감지 -> 그 가격 이상의 지정가 소진 (백테스트 taken 규칙)
    #  v8 이 주문했던 종목이 보유로 넘어왔으면 체결된 것이다.
    for h in holdings:
        code = h.get('stk_cd')
        if code in _ordered_codes and code not in open_buy:
            px = float(h.get('avg_price') or 0)
            if px > 0:
                consume_limits(code, px)
                qty = int(h.get('qty') or 0)
                delta = _take_fill_delta(code, qty)
                if delta > 0:
                    asset_ratio = (px * delta / equity) if equity > 0 else None
                    _record_trade(code, h.get('stk_nm'), 'buy', 'v8_buy', delta, px, px, 0.0,
                                  asset_ratio=asset_ratio)
                    _log.info('v8 매수체결 기록 %s qty=%d(누적%d) px=%.0f', code, delta, qty, px)

    # 하루 1회 계산된 캐시를 쓴다 (첫 사이클에서만 pkl 을 읽는다)
    #  · 보유 중 종목 제외      = 동일 종목 중복 보유 금지
    #  · 당일 매도 종목 제외    = sequential_filter 의 두 번째 규칙
    _sold = sold_today_codes()
    cands = [c for c in daily_candidates()
             if c['code'] not in held and c['code'] not in _sold]

    # ── 후보에서 빠진 종목의 미체결 주문 취소
    #  '후보 이탈'은 세 가지뿐이다.
    #   (1) 10 거래일 만료로 pending 에서 삭제됨 (15:55 스크리닝 때만 발생)
    #   (2) 주가가 올라 지정가가 오늘 하한가보다 낮아짐 -> 오늘은 주문 불가
    #   (3) pkl 로드 실패
    #  (2)는 전일 종가가 기준이라 **장중에는 바뀌지 않는다.** 즉 이 취소는 사실상
    #  아침 첫 사이클에서만 동작하는 정리 작업이다.
    #  보유로 바뀐 종목(=부분 체결)의 잔량은 **취소하지 않는다.** 백테스트는 전량 체결을
    #  가정하므로 남은 수량이 마저 체결되는 편이 원본에 가깝다.
    keep_codes = {c['code'] for c in cands}
    for code, u in list(open_buy.items()):
        if code in held:
            continue                      # 부분 체결 잔량 — 그대로 둔다
        if code in keep_codes:
            continue
        try:
            api.cancel_order(u['ord_no'], code, int(u.get('oso_qty') or 0), side='1')
            # ⚠️ open_buy 에서 빼야 한다. 아래에서 placed = len(open_buy) 로 현재 주문 수를
            #    세기 때문에, 취소한 주문이 남아 있으면 자리가 없다고 판단해 새 주문을 못 낸다.
            open_buy.pop(code, None)
            release_ordered(code)         # 체결 없이 취소됐으니 소유권도 해제
            _log.info('v8 주문취소 %s (후보이탈)', code)
        except Exception as e:
            _log.warning('주문취소 실패 %s: %s', code, e)

    room = SLOTS - len(held)
    if room <= 0:
        return

    # ── 주문 순서 ────────────────────────────────────────────────────────────
    # 예수금이 미체결 주문에 묶이므로 동시에 걸 수 있는 건 8~10개뿐인데 후보는 200개가 넘는다.
    # 즉 '어느 것에 주문을 걸까'를 골라야 하고, 이건 백테스트가 답을 주지 않는 문제다.
    # 백테스트는 도달 가능한 후보 전부를 대기시켜 두고 '실제로 지정가에 닿은 것'이 체결됐다.
    # 랭킹 점수는 같은 날 체결이 슬롯보다 많을 때 고르는 용도였다(용량 제약 해결).
    #
    # 그래서 gap(오늘 지정가에 닿으려면 필요한 하락폭)을 1순위로 둔다.
    # 체결 건수를 최대화하는 쪽이 백테스트 노출도에 가장 가깝기 때문이다.
    # 점수는 gap 이 비슷한 것들 사이의 동순위 판정에만 쓴다(GAP_TIE_BUCKET 단위로 묶음).
    #   'score' 로 바꾸면 gap 상위 GAP_PREFILTER 개 안에서 점수 순으로 고른다.
    #   그쪽은 체결 건수가 줄어드는 대신 백테스트 랭킹 기준에 충실하다.
    if WATCH_PRIORITY == 'score':
        head = sorted(cands, key=lambda x: -x['gap'])[:max(room, GAP_PREFILTER)]
        cands = sorted(_rank(head), key=lambda x: -x['score'])
    else:
        cands = _rank(cands)
        # gap 을 버킷으로 내림 → 같은 버킷 안에서만 점수가 순서를 가른다
        cands.sort(key=lambda x: (-round(x['gap'] / GAP_TIE_BUCKET), -x['score']))

    # ── 장중 보정 ────────────────────────────────────────────────────────────
    # gap 은 전일 종가 기준이라 장중에 변하지 않는다. 그런데 '지정가까지 남은 거리'는
    # 하루 종일 변한다. 아침 gap 이 -20% 여도 오전에 -15% 빠졌으면 남은 거리는 -6% 다.
    # 그 종목은 아침 gap 이 -9% 인데 하루 종일 오른 종목보다 훨씬 체결에 가깝다.
    # 아침 순위만 쓰면 이 역전을 놓친다.
    #
    # 그래서 아침 gap 상위 LIVE_REGAP_TOP 개의 현재가를 조회해 live_gap 으로 다시 세운다.
    #   live_gap = 지정가/현재가 - 1     (0 이상 = 이미 지정가 이하 → 즉시 체결권)
    # 호출 비용: 60개 x 0.143초 = 약 8.6초. LIVE_REGAP_EVERY_SEC 주기로만 수행한다.
    # 걸어둔 주문이 하나도 없으면(개장 직후, 또는 전부 체결된 뒤) 주기를 무시하고 즉시 수행한다.
    global _last_regap_ts
    now_ts = time.time()
    do_regap = LIVE_REGAP and (not open_buy
                               or now_ts - _last_regap_ts >= LIVE_REGAP_EVERY_SEC)
    if do_regap:
        _last_regap_ts = now_ts
        for i, c in enumerate(cands):
            if i >= LIVE_REGAP_TOP:
                c['cur_px'] = 0
                c['live_gap'] = c['gap']
                continue
            try:
                px = int(api.get_current_price(c['code']) or 0)
            except Exception:
                px = 0
            c['cur_px'] = px
            c['live_gap'] = (float(c['ord_px']) / px - 1.0) if px > 0 else c['gap']
        cands.sort(key=lambda x: (-round(x['live_gap'] / GAP_TIE_BUCKET), -x['score']))
    else:
        for c in cands:
            c['cur_px'] = 0
            c['live_gap'] = c['gap']

    amt = equity * ALLOC

    # ── 이미 걸린 주문을 '지금 자금' 기준으로 다시 맞춘다.
    #  주문은 낼 때의 자금으로 수량이 정해지는데, 실제 체결은 며칠 뒤일 수 있다.
    #  그 사이 평가자산이 변하면 백테스트(체결 시점 자산의 10%)와 어긋나므로
    #  RESIZE_TOL 이상 벌어지면 취소 후 재주문한다.
    for c in cands:
        u = open_buy.get(c['code'])
        if not u or c['code'] in held:
            continue
        cur_qty = int(u.get('oso_qty') or 0)
        tgt_qty = int(amt // c['ord_px'])
        if tgt_qty < 1 or cur_qty < 1:
            continue
        if abs(cur_qty - tgt_qty) / float(tgt_qty) <= RESIZE_TOL:
            continue
        try:
            api.cancel_order(u['ord_no'], c['code'], cur_qty, side='1')
            res = buy_limit(c['code'], tgt_qty, c['ord_px'])
            _log.info('v8 수량조정 %s %d -> %d주 (자금변동) -> %s',
                      c['code'], cur_qty, tgt_qty, res)
            _mark_ordered(c['code'])
            # ⚠️ open_buy 에서 빼지 않는다. 취소 후 곧바로 다시 걸었으므로 주문은 여전히
            #    살아 있다. 빼면 placed 가 실제보다 작아져 주문을 하나 더 내고 예수금이 모자란다.
            #    다만 주문번호/수량이 바뀌었으니 갱신해 둔다(같은 사이클의 교체 로직이 쓴다).
            if isinstance(res, dict) and res.get('ord_no'):
                u['ord_no'] = res['ord_no']
            u['oso_qty'] = tgt_qty
        except Exception as e:
            _log.warning('수량조정 실패 %s: %s', c['code'], e)

    slots_for_orders = min(MAX_OPEN_ORDERS, room, int(cash // amt) if amt > 0 else 0)
    placed = len(open_buy)

    for c in cands:
        if c['code'] in open_buy:
            continue
        if amt < MIN_ORDER:
            break
        qty = int(amt // c['ord_px'])
        if qty < 1:
            continue

        if placed >= slots_for_orders:
            # 자리가 없다. 장중에 급락해서 훨씬 가까워진 후보라면, 주문중인 것 중
            # 가장 먼 것과 교체한다. 취소는 호가 대기순번을 잃는 손해가 있으므로
            # REGAP_MARGIN 이상 확실히 더 가까울 때만 바꾼다.
            # 이번 사이클에 현재가를 실제로 조회했을 때만 교체를 허용한다.
            # 조회를 건너뛴 사이클의 live_gap 은 아침 gap 으로 되돌아가 있으므로,
            # 그 값으로 교체하면 방금 내린 판단을 낡은 기준으로 되돌리게 된다.
            if not do_regap:
                break
            worst = None
            for o in cands:
                if o['code'] not in open_buy:
                    continue
                if worst is None or o['live_gap'] < worst['live_gap']:
                    worst = o
            if worst is None or (c['live_gap'] - worst['live_gap']) < REGAP_MARGIN:
                break
            u = open_buy[worst['code']]
            try:
                api.cancel_order(u['ord_no'], worst['code'],
                                 int(u.get('oso_qty') or 0), side='1')
            except Exception as e:
                _log.warning('교체용 취소 실패 %s: %s', worst['code'], e)
                break
            _log.info('v8 주문교체 %s(남은 %.1f%%) -> %s(남은 %.1f%%)',
                      worst['code'], worst['live_gap'] * 100,
                      c['code'], c['live_gap'] * 100)
            open_buy.pop(worst['code'], None)
            release_ordered(worst['code'])
            placed -= 1

        res = buy_limit(c['code'], qty, c['ord_px'])
        ok = isinstance(res, dict) and str(res.get('return_code', '')) == '0'
        _log.info('v8 지정가주문 %s %s qty=%d @%d (아침 %.1f%% / 현재 %.1f%%) -> %s',
                  c['code'], '접수' if ok else '거부', qty, c['ord_px'],
                  c['gap'] * 100, c['live_gap'] * 100,
                  res.get('return_msg') if isinstance(res, dict) else res)
        if ok:
            placed += 1
            _mark_ordered(c['code'])


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    if len(sys.argv) > 1 and sys.argv[1] == 'screen':
        st = run_v8_screen()
        print('대기 후보 %d건' % len(st['pending']))
        for k, v in list(st['pending'].items())[:10]:
            v = _migrate(v)
            print('  %s 종가 %.0f -> 지정가 %s'
                  % (k, v.get('sig_close') or 0,
                     ' '.join('%d(age%d)' % (e['limit'], e.get('age', 0))
                              for e in sorted(v['limits'], key=lambda x: -x['limit']))))
    else:
        run_v8_buy_cycle()
