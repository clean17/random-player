# -*- coding: utf-8 -*-
"""
fire(급상승 관심종목) 자동 매수 전략.

매수 조건 (2026-08-05 기준):
  1. 시장폭 레짐 ON      : 전 종목 중 종가>MA20 비율 >= 40% (BREADTH_MIN). 미만이면 그날 진입 전면 차단
  2. fire 쿼리 통과      : get_interest_stocks_info(오늘-6일 ~ 오늘)를 총상승률 내림차순으로 받음.
                           쿼리 자체 조건(총상승률 8~12%, 당일 3~12%, 고점 대비 -3% 이내,
                           시총 700억↑, 거래대금 40억↑ 등)은 SQL에 있음
  3. reserved 교집합     : 위를 통과한 종목 중, 관심종목 화면에서 '자동매수 대상'으로 체크한
                           종목(reserved_stocks, flag=true)만 남긴다. 체크한 게 없으면 그날 매수 없음.
                           체크했어도 fire 조건을 못 넘기면 사지 않는다(교집합).
                           스케줄러엔 로그인 세션이 없어 user 구분 없이 flag=true 전체를 본다.
  4. 쿨다운 제외         : COOLDOWN_DAYS(2일) 내 재매수면 skip (1일에 샀으면 3일에 재매수 가능).
                           이미 보유 중인 종목도 fire 조건을
                           다시 통과하고 쿨다운만 지나면 추가 매수한다(2026-08-10부터, 종전엔 보유
                           중이면 무조건 skip). 추가매수로 평단가가 바뀌면 트레일링 상태는
                           kiwoom_trailing_stop.py의 evaluate_and_trade()가 새 평단가 기준으로
                           자동 리셋한다.
  5. 사이징             : 기준은 총자산이 아니라 '가용 현금'(총자산 - 보유종목 평가금액).
                           가용현금 × CASH_DEPLOY_RATIO(70%)가 그날 매수한도(deploy_limit).
                           예산은 후보마다 '남은 한도 ÷ 남은 후보 수'로 재계산하고,
                           종목당 상한 = 한도 ÷ POS_CAP_DIVISOR(12) = 가용현금의 5.8%로 제한한다.
                           하루 최대 BUY_SLOTS(20)종목. 배정 예산보다 주가가 비싸면(1주도 못 삼)
                           그 종목은 skip하고 그 예산은 뒤 후보로 흘러간다.
                           ⚠️ CASH_DEPLOY_RATIO는 '보유 목표 비율'이 아니라 '그날 남은 현금 중
                              신규 매수에 쓸 최대 비율'이다. 평균 보유 2.28일이면 정상상태 보유비율은
                              u = h·r/(1+h·r)이라 r=0.70의 이론 상한이 61.5%다 — r=0.70으로
                              '자산의 70% 보유'는 구조적으로 불가능하다.

쿨다운/슬롯 재검증 (2026-08-10, 포트폴리오 레벨 재시뮬레이션 — 246거래일 하루 단위 현금흐름 +
보유중 추가매수 반영. 1차는 초기자본 1000만원, 2차는 3천만원 가정):
  - 정렬방향: 낮은순이 슬롯7/15/20에서 모두 무작위·높은순을 압도(예: 슬롯20 기준 낮은순 +3.0%
    vs 무작위 -10.9% vs 높은순 -35.0%). 총상승률 '낮은순'을 계속 유지하는 근거.
  - 슬롯수: 7보다 15~20이 뚜렷하게 낫다(슬롯7 -9.7% → 슬롯15 -4.9% → 슬롯20 +3.0%, 유일하게
    양수·Sharpe+0.25). 다만 슬롯10만 예외적으로 나쁘게 나왔는데(-22.7%), 다른 슬롯에서
    정렬효과가 워낙 크고 일관돼서 이건 1개 경로짜리 백테스트의 노이즈로 판단하고 20을 택함.
  - 쿨다운 1차: 3일보다 0~2일이 전부 낫다(0일/1일 -18.8%, 2일 -18.4%, 3일 -22.7%, 1000만원 기준).
  - 쿨다운 2차(3천만원, 슬롯20): 0일(완전제거) +2.2%p 아니라 오히려 -0.6% ←→ 2일 +2.2%로 더 좋음.
    쿨다운을 완전히 빼면 낮은순위 후보 하나에 추가매수가 거의 매일 몰려(추가매수 641건 vs 2일일
    때 530건) 집중도가 과해지고 분산 효과가 줄었다 — 쿨다운이 자연스러운 분산 장치로도 작동한다.
    그래서 0일이 아니라 2일로 최종 확정.
  ⚠️ 계좌 자산이 작으면(예 300만원대) 슬롯20은 슬롯당 예산이 너무 작아져 매수 시도의 40%+가
     "1주도 못 사서" 버려진다(nocash율). 계좌가 3,000만원 이상일 때 슬롯20이 감당 가능한 걸로
     검증됨 — 계좌 규모가 그보다 작다면 슬롯을 줄이는 걸 고려할 것.
     3천만원 기준으로는 오히려 슬롯25(+4.4%, Sharpe0.30)가 20(-0.6%)보다 낫게 나왔다 — 계좌가
     실제로 3천만원 근처가 되면 슬롯을 20→25로 다시 올리는 걸 검토할 것(2026-08-10 기준 계좌는
     아직 700만원대라 지금은 20 유지).

사이징 재검증 (2026-08-11, auto_trading/backtest/fire_sizing_backtest.py — 201거래일 하루단위 현금흐름):
  계기: 2026-08-11 15:18 실매매에서 후보 18종목 중 7종목이 '1픽 예산(131,276원) < 현재가'로 skip돼
  11종목·한도의 47.5%만 집행하고 250만원이 남았다. 원인은 slot_budget을 루프 밖에서 한 번만
  계산해 skip된 슬롯 예산이 재분배되지 않는 것이었다.
  - 예산 재분배 방식은 '순차(남은한도/남은후보)'가 '균등(살 수 있는 후보 수로 나눠 동일 배분)'보다
    일관되게 우수했다. 균등안은 2026-04~07 구간에서 -6.9%로 현행(-6.8%)보다도 나빠 기각.
  - 종목당 상한은 필수다. 상한 없이 재분배하면 후보가 1개인 날(201일 중 7일)에 한도 전액이 한
    종목에 들어가 단일종목이 자본의 83%가 되고 MDD가 -13.8% → -26.9%로 2배가 된다.
  - reserved 20종목 유지를 전제로 divisor는 10으로 확정했다. 후보를 reserved 규모(20)로 제한하고
    랜덤 선정 5회 평균(760만원, r=0.70):
      divisor  8 : 총수익 34.4%  Sharpe 1.82  MDD -15.1%  한도소진 78.1%  현금 30.1%
      divisor 10 : 총수익 35.2%  Sharpe 1.98  MDD -13.2%  한도소진 71.8%  현금 34.3%  ← 채택
      divisor 12 : 총수익 33.9%  Sharpe 2.05  MDD -12.4%  한도소진 65.9%  현금 38.3%
      divisor 14 : 총수익 32.0%  Sharpe 2.06  MDD -12.0%  한도소진 60.6%  현금 42.0%
      divisor 20 : 총수익 25.0%  Sharpe 2.00  MDD -11.4%  한도소진 45.9%  현금 52.6%
    10이 총수익 1위이고 '낮은순으로만 reserved를 고른' 케이스에서도 1위(28.8%)라 선정 방식에
    robust하다. 12가 Sharpe·MDD는 약간 낫다(2.05/-12.4) — 현금을 더 남기는 대신 안정성을
    택하려면 12로 되돌리면 된다.
  - BUY_SLOTS는 20 유지. reserved 20종목이면 후보가 20을 넘지 못해 슬롯 25는 결과가 완전히
    동일하다(총수익·Sharpe·체결수 소수점까지 같음). 슬롯을 늘리는 건 reserved를 20개보다
    많이 유지할 때만 의미가 있다.
  - 아래 표는 후보를 제한하지 않은(fire 픽 전체 = 일평균 13.2종목) 조건이라 reserved 20 전제와
    다르다. divisor 선택은 위 표를 근거로 했고, 아래는 상한 자체의 필요성 근거로만 본다:
      현행(한도/20 고정)  총수익 19.5%  Sharpe 1.60  MDD -13.8%  보유비율 48.5%
      순차+상한20         21.7%        1.90        -12.2%       45.5%
      순차+상한12         32.0%        2.05        -12.2%       58.9%   ← 채택
      순차+상한10         33.5%        1.98        -12.9%       62.8%
      순차+상한8          33.2%        1.83        -14.3%       66.9%
    8 이하는 하락 구간(2026-04~07, 3천만원)에서 -8.1%로 현행 -7.0%보다 나빠져 배제했다. 상한을
    풀면 순차 재분배의 정렬 편향(금액가중 total_rate가 16.79까지, 현행 15.48)이 커지는데 그게
    하락장에서 독이 된다 — 위 '정렬방향: 높은순 -35%'와 방향이 같다.
  - 계좌 규모 효과가 아니다: 300만~3억까지 훑어도 상한12 우위가 +11~+19%p로 유지된다.
    nocash율은 19.0%(300만) → 0.0%(3억)로 사라지는데 우위는 그대로다.
  - 노출(보유비율) 확대 효과도 아니다: 보유비율을 ~60%로 맞춰 비교하면
      현행 + ratio 1.00   보유 62.1%  총수익 19.1%  Sharpe 1.26  MDD -16.9%
      상한12 + ratio 0.70 보유 58.9%  총수익 32.0%  Sharpe 2.05  MDD -12.2%
    같은 노출에서 13%p 차이난다. '남은한도/남은후보'가 후보 수에 반비례하는 자동 사이징이어서,
    후보가 적은 날(신호 희소)엔 크게 후보가 많은 날(시장 과열)엔 작게 산다. 후보수 구간별 투입은
    수익구간(후보 20개 이하, +0.45~0.64%/건) +16~19%, 손실구간(후보 31개+, -0.94%/건) -52%로
    이동한다. 반대로 현행에서 CASH_DEPLOY_RATIO만 올리면 모든 구간에 균등하게 더 넣어
    손실구간 투입까지 늘어 Sharpe가 1.60 → 1.26으로 무너진다.
  ⚠️ 한계: reserved 교집합을 재현할 수 없어 fire 픽 전체를 후보로 가정했다(그래서 위 '쿨다운/슬롯
     재검증'의 수치와 재현되지 않는다 — 현행 슬롯20이 여기선 +19.5%, 거기선 +3.0%. 두 표를
     나란히 비교하면 안 된다). 보유 포지션을 취득원가로 평가해 노출 큰 설정의 MDD가 과소평가된다.
     왕복비용 0.2%를 넣으면 현행 19.5→8.3%, 상한12 32.0→약 절반으로 깎인다(고회전 2,100건).

백테스트 근거 (fire_backtest_result.csv, 2025-09 ~ 2026-07, 2,658건):
  - fire 픽 전체 매수: 평균 +0.39%/건 (수수료 빼면 본전 이하)
  - H2 필터(20일 신고가 -1.6% 이내 + 당일 등락률 +12% 이상): 평균 +2.75%, 승률 48.6%
  - H2 + 시장폭 레짐: 평균 +3.50%, 승률 53%, 9개월 전부 플러스

  ⚠️ 2026-08-05 요청으로 H2 필터를 제거함. 위 백테스트 기준으로는 H2 없는 'fire 픽 전체 매수'가
     평균 +0.39%/건(수수료 차감 시 본전 이하) 구간에 해당한다. 다만 그 수치는 fire 픽 전체를 대상으로
     한 것이고 지금은 총상승률 상위 10개로 한정 + 레짐 필터가 남아 있어 완전히 같은 조건은 아니다.
     성과는 재검증이 필요하며, 되돌리려면 get_fire_candidates()에 _daily_metrics() 조건을 다시 걸면 된다.

진입 시점 (중요):
  백테스트의 매수가는 신호일 '종가'다(fire_backtest_result.csv의 buy 컬럼 = 해당일 종가로 확인됨).
  H2 필터도 20일 신고가 대비/당일 등락률이라 완성된 일봉을 전제한 지표다. 따라서 이 전략은
  장 마감 직전 1회만 평가/매수한다 (batch_runner의 kiwoom_fire_buy 잡, 평일 15:18).
  예전처럼 장중 :15/:35/:55로 21번 돌리면 아직 절반만 만들어진 일봉으로 판단하게 되고,
  급등 중인 장중 고점을 추격해 하루 매수 한도(BUY_SLOTS)를 아침에 소진한다. 실제로 2026-07-24
  HD현대에너지솔루션은 10:35에 196,600원에 샀는데 그날 종가가 164,000원(-16.6%),
  SK오션플랜트는 10:55에 20,450원에 샀는데 종가 18,350원(-10.3%)이었다.

매수 후 청산은 kiwoom_trailing_stop.py의 30초 잡이 자동으로 담당한다.
2026-08-11 확인한 실제 값 (기존 '손절 -3% / 트레일링 -2%p' 표기는 코드와 달라 수정):
  STOP_LOSS_RATE=-0.06, TARGET_RATES=[](목표가 없음),
  TRAIL_ACTIVATE_RATE=+0.07 / TRAIL_GAP=0.05 / MIN_PROFIT_FLOOR=0.03.

실전 전 반드시 KIWOOM_ENV=mock으로 검증할 것.
"""
import os
import json
import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

from auto_trading.kiwoom_api import buy_market, get_holdings_and_summary, get_account_credentials
from auto_trading.kiwoom_trailing_stop import _log, _record_trade, is_market_open, order_accepted

# ── 전략 파라미터 ────────────────────────────────────────────────────────────
CHECK_DISPLAY_LIMIT = 20   # --check로 후보를 출력할 때만 쓰는 표시 개수 제한 (매수 로직과 무관)
BREADTH_MIN = 0.0          # 시장폭 레짐 게이트. 0 이하면 게이트를 아예 끈다(현재 OFF).
                           # breadth 값은 참고/로그용으로 계속 계산된다.
                           # 켤 때 참고한 검증치(2026-06~08 데이터, 3,045건):
                           #   0.40 → 2026-07에 135건 통과시켜 -3.06%, 2026-03도 못 막음(-2.73%)
                           #   0.50 → 6·7월 거래 0건으로 차단, 다만 42거래일 중 진입 가능일이 2일뿐
                           # breadth 방향(전일대비 상승/이평 상회)을 쓰는 안도 테스트했으나
                           # 검증기간 전부 마이너스(-1.6~-2.1%)라 폐기 — 수준(level)만 유효했다.
FIRE_WINDOW_DAYS = 6       # fire 집계 기간 (오늘-6일 ~ 오늘, 프론트 '관심' 탭과 동일)
CASH_DEPLOY_RATIO = 0.70   # 가용 현금 중 자동매수에 쓸 최대 비율 (나머지 30%는 현금 버퍼로 남김)
BUY_SLOTS = 20             # 하루 최대 신규 매수 종목 수. 7→20 (2026-08-10, 포트폴리오
                           # 재시뮬레이션 근거는 위 docstring "쿨다운/슬롯 재검증" 참고).
                           # 2026-08-11부터 '1픽 예산의 분모'가 아니라 종목 수 상한으로만 쓴다
                           # (예산은 POS_CAP_DIVISOR가 결정).
POS_CAP_DIVISOR = BUY_SLOTS  # 종목당 상한 = 매수한도 / 20 = 가용현금의 3.5%.
                           # ⚠️ 2026-08-11: 한때 10으로 내렸다가 되돌렸다. 근거였던
                           # fire_backtest_result.csv가 목표가 +15%가 살아 있던 구버전 규칙이라
                           # 건당 기대값을 +0.39%로 과대평가하고 있었다. 현재 청산규칙으로 재생성한
                           # CSV(auto_trading/backtest/fire_backtest_regen.py)에서는 기대값이 0 근처(-0.74% ~ +0.16%,
                           # 일중 근사의 비관/낙관 극단)이고, 그 조건에서는 상한을 풀수록 손실이
                           # 커진다(divisor 10이 20보다 비관 -12.2%p / 낙관 -17.0%p 나쁨).
                           # 기대값이 0 이하인 전략에서는 노출을 늘리는 쪽이 항상 불리하다.
                           # 상한을 다시 풀려면 기대값이 확실히 플러스임을 먼저 입증해야 한다.
                           # reserved가 20개 이하인 동안 이 값(=BUY_SLOTS)은 아래 순차 재분배를
                           # 무력화해 2026-08-11 이전 동작과 정확히 같아진다.
COOLDOWN_DAYS = 2          # 같은 종목 재매수 금지 기간. 1일에 샀으면 3일에 재매수 가능. 3→2
                           # (아래 조건이 "<"라서: diff=(오늘-마지막매수일).days, diff < 2이면 skip.
                           #  1일 매수 → 2일 diff1 skip, 3일 diff2 → 재매수 허용)

PKL_DIR = r'C:\my-project\AutoSales.py\data\pickle'
_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs', 'kiwoom_trading')
BREADTH_CACHE = os.path.join(_LOG_DIR, 'market_breadth_cache.json')
FIRE_STATE_FILE = os.path.join(os.path.dirname(__file__), 'kiwoom_fire_state.json')

ACNT_NO, ACNT_PWD = get_account_credentials()


# ── 시장폭(breadth) 레짐 ─────────────────────────────────────────────────────

def _compute_breadth() -> Optional[Tuple[str, float]]:
    """전 종목 pkl 스캔: 최신일 기준 (종가 > MA20) 종목 비율. (date_iso, ratio) 반환.
    2,800여 파일을 읽어 2~3분 걸리므로 하루 1회 캐시해서 쓴다."""
    files = [f for f in os.listdir(PKL_DIR) if f.endswith('.pkl')]
    per_date = {}  # date -> [above, total]
    for fname in files:
        try:
            df = pd.read_pickle(os.path.join(PKL_DIR, fname))
            c = df.iloc[:, 3].dropna()  # 종가
            if len(c) < 21:
                continue
            last_date = c.index[-1]
            ma20 = c.tail(20).mean()
            a = per_date.setdefault(last_date, [0, 0])
            a[1] += 1
            if c.iloc[-1] > ma20:
                a[0] += 1
        except Exception:
            continue
    if not per_date:
        return None
    # 파일별 마지막 일자가 다를 수 있으므로(상폐 등) 가장 최신 일자 기준
    latest = max(per_date.keys())
    above, total = per_date[latest]
    if total < 500:
        return None
    return latest.date().isoformat(), above / total


def get_market_breadth(force: bool = False) -> Optional[float]:
    """오늘자 breadth 반환 (일 1회 계산 후 캐시)."""
    today = datetime.date.today().isoformat()
    if not force and os.path.exists(BREADTH_CACHE):
        try:
            with open(BREADTH_CACHE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            if cache.get('date') == today:
                return cache.get('breadth')
        except (json.JSONDecodeError, OSError):
            pass
    result = _compute_breadth()
    if result is None:
        return None
    data_date, breadth = result
    with open(BREADTH_CACHE, 'w', encoding='utf-8') as f:
        json.dump({'date': today, 'data_date': data_date, 'breadth': breadth}, f)
    _log.info(f'[레짐] 시장폭(종가>MA20 비율)={breadth:.1%} (데이터 기준일 {data_date})')
    return breadth


# ── fire 후보 + H2 필터 ─────────────────────────────────────────────────────

def _daily_metrics(stk_cd: str) -> Optional[Tuple[float, float]]:
    """(dist_20d_high %, ret_1d %) 반환 — 로그/사후분석용 참고 지표. 매수 필터로는 쓰지 않는다.
    pkl 데이터가 오늘자가 아니면 None (장중 20분 주기 갱신 전제)."""
    path = os.path.join(PKL_DIR, '{}.pkl'.format(stk_cd))
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_pickle(path)
    except Exception:
        return None
    df = df.iloc[:, :4]
    df.columns = ['open', 'high', 'low', 'close']
    df = df.dropna()
    if len(df) < 21:
        return None
    if df.index[-1].date() != datetime.date.today():
        return None  # 오늘 데이터 아직 없음 (fetch_stock_data 갱신 전)
    close = df['close'].iloc[-1]
    prev_close = df['close'].iloc[-2]
    high20 = df['high'].tail(20).max()
    if high20 <= 0 or prev_close <= 0:
        return None
    dist = (close / high20 - 1) * 100
    ret1d = (close / prev_close - 1) * 100
    return dist, ret1d


def _parse_pct(value) -> Optional[float]:
    """SQL이 '10.5%' 처럼 문자열로 내려주는 퍼센트 값을 float로. 파싱 불가면 None."""
    if value is None:
        return None
    try:
        return float(str(value).replace('%', '').replace(',', '').strip())
    except ValueError:
        return None


def get_fire_candidates(limit: Optional[int] = None) -> List[Dict]:
    """fire 쿼리(SQL 조건 통과) 결과를 총상승률 '오름차순'(낮은 순)으로 반환.

    정렬이 곧 매수 대상 선정이다 — run_fire_buy_cycle()이 이 순서대로 훑다가 BUY_SLOTS(20)를
    채우면 멈추기 때문. SQL의 ORDER BY는 DESC(높은 순)지만 그건 웹 화면(관심/즐겨찾기/자동매수 탭)이
    공유하는 표시 순서라 건드리지 않고, 매수용 순서만 여기서 뒤집는다.

    근거(2026-06~08, 3,255건을 실제 청산규칙으로 시뮬레이션, 수수료 차감 후 / 매일 상위 7종목):
      총상승률 높은 순(기존)  +0.77%   ← 무작위(30회 평균 +0.85%)보다도 낮음
      무작위 30회 평균        +0.85%
      총상승률 낮은 순(현재)  +2.35%   ← 30회 무작위 전부를 상회, 6·7·8월 모두 플러스
    많이 오른 종목을 쫓는 것보다 덜 오른 종목을 담는 쪽이 유리했다.

    limit은 출력용 제한일 뿐, 매수 경로에서는 자르지 않는다 — 자르면 내가 체크한(reserved) 종목이
    순위가 낮다는 이유로 조용히 제외돼 '체크했는데 왜 안 사지?'가 되기 때문.
    (예전엔 여기서 H2 필터로 한 번 더 걸렀으나 2026-08-05 요청으로 제거 — 상단 docstring 참고)"""
    from app.repository.stocks.stocks import get_interest_stocks_info
    today = datetime.date.today()
    start = (today - datetime.timedelta(days=FIRE_WINDOW_DAYS)).isoformat()
    rows = get_interest_stocks_info(start, today.isoformat())

    candidates = []
    for row in rows:
        stk_cd = str(row.get('stock_code') or '').zfill(6)
        if not stk_cd or stk_cd == '000000':
            continue
        metrics = _daily_metrics(stk_cd)  # 참고 지표(로그용) — 없어도 매수는 진행
        candidates.append({
            'stk_cd': stk_cd,
            'stk_nm': row.get('stock_name'),
            'total_rate': row.get('total_rate_of_increase'),
            '_total_rate_num': _parse_pct(row.get('total_rate_of_increase')),
            'dist_20d_high': round(metrics[0], 2) if metrics else None,
            'ret_1d': round(metrics[1], 2) if metrics else None,
        })

    # 총상승률 낮은 순. 파싱 실패(None)는 맨 뒤로 보내 우선 매수되지 않게 한다.
    candidates.sort(key=lambda c: (c['_total_rate_num'] is None, c['_total_rate_num']))

    if limit is not None:
        candidates = candidates[:limit]
    return candidates


# ── 자동 매수 사이클 ─────────────────────────────────────────────────────────

def _load_fire_state() -> Dict:
    if not os.path.exists(FIRE_STATE_FILE):
        return {}
    try:
        with open(FIRE_STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_fire_state(state: Dict):
    with open(FIRE_STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def run_fire_buy_cycle():
    """장중 주기 실행: 레짐 확인 → fire+H2 후보 → 쿨다운/보유중/일일한도 거르고 시장가 매수."""
    if not (ACNT_NO and ACNT_PWD):
        _log.error('[fire] 계좌 정보 미설정')
        return

    # BREADTH_MIN <= 0 이면 레짐 게이트 자체를 끈다. 이때 breadth 계산 실패(None)로도 매수를
    # 막지 않는다 — 게이트를 껐는데 계산 실패 때문에 조용히 안 사는 상황을 피하기 위함.
    breadth = get_market_breadth()
    if BREADTH_MIN > 0:
        if breadth is None:
            _log.error('[fire] 시장폭 계산 실패 — 진입 보류')
            return
        if breadth < BREADTH_MIN:
            return  # 레짐 OFF: 조용히 스킵 (레짐 상태는 breadth 계산 시 하루 1회 로그됨)

    candidates = get_fire_candidates()
    if not candidates:
        return

    # 자동매수 대상(reserved) 교집합 — 화면(관심종목 뷰)에서 체크한 종목만 실제로 매수한다.
    # fire SQL 조건을 통과한 것 중에서 고르는 방식이라, 체크했더라도 그날 조건을 못 넘기면 안 산다.
    from app.repository.stocks.stocks import get_reserved_stock_codes
    try:
        reserved = get_reserved_stock_codes()
    except Exception as e:
        # 조회 실패 시 '전 종목 매수'로 흘러가면 안 되므로 보수적으로 중단
        _log.error(f'[fire] reserved 목록 조회 실패 — 매수 보류: {e}')
        return

    if not reserved:
        _log.info('[fire] 자동매수 대상(reserved)으로 체크된 종목이 없어 매수하지 않음')
        return

    passed = len(candidates)
    candidates = [c for c in candidates if c['stk_cd'] in reserved]
    _log.info(f'[fire] fire 조건 통과 {passed}종목 / reserved {len(reserved)}종목 '
              f'→ 교집합 {len(candidates)}종목')
    if not candidates:
        return

    state = _load_fire_state()
    today = datetime.date.today()
    daily = state.get('_daily', {})
    buys_today = daily.get('count', 0) if daily.get('date') == today.isoformat() else 0
    if buys_today >= BUY_SLOTS:
        return

    bd_txt = f'{breadth:.0%}' if breadth is not None else 'n/a'  # 레짐 OFF면 None일 수 있음

    _, summary = get_holdings_and_summary(ACNT_NO, ACNT_PWD)

    # 사이징 기준은 총자산이 아니라 '가용 현금'. 그중 CASH_DEPLOY_RATIO(70%)까지만 쓰고
    # 나머지는 손대지 않는다(버퍼). deployed 누적으로 총 사용액이 그 한도를 넘지 않도록 막는다.
    cash = summary['total_asset'] - summary['tot_evlt_amt']
    deploy_limit = max(0.0, cash) * CASH_DEPLOY_RATIO
    # 종목당 상한 (2026-08-11 도입). 재분배가 소수 종목에 몰리는 것을 막는 안전장치이자
    # 실질 사이징 기준. 근거는 위 docstring '사이징 재검증' 참고.
    pos_cap = deploy_limit / POS_CAP_DIVISOR if POS_CAP_DIVISOR > 0 else deploy_limit
    deployed = 0.0

    if pos_cap <= 0:
        _log.info(f'[fire] 가용 현금 부족 — 현금 {cash:,.0f}원, 매수 예산 {deploy_limit:,.0f}원')
        return

    # 쿨다운 제외는 예산 배분 '전에' 끝내야 한다 — 아래 재분배 분모가 '남은 후보 수'라서,
    # 어차피 사지 않을 종목이 분모에 남아 있으면 예산이 실제보다 잘게 쪼개진다.
    # 2026-08-10 재검증: 쿨다운을 0일(완전 제거)로 뺐다가 도로 2일로 되돌림 — 포트폴리오
    # 시뮬레이션(3천만원/슬롯20)에서 0일이 2일보다 더 나빴다(-0.6% vs +2.2%). 쿨다운이 없으면
    # 낮은순위 후보 하나에 추가매수가 거의 매일 몰려(추가매수 641건 vs 530건) 집중도가 과해지고
    # 분산 효과가 줄었다 — 쿨다운이 자연스러운 분산 장치로도 작동하고 있었다는 뜻.
    live = []
    for cand in candidates:
        last_buy = state.get(cand['stk_cd'])
        if last_buy:
            try:
                if (today - datetime.date.fromisoformat(last_buy)).days < COOLDOWN_DAYS:
                    continue
            except ValueError:
                pass
        live.append(cand)

    _log.info(f'[fire] 후보 {len(candidates)}종목(쿨다운 제외 후 {len(live)}종목) / '
              f'가용현금 {cash:,.0f}원 → 매수한도 {deploy_limit:,.0f}원({CASH_DEPLOY_RATIO:.0%}), '
              f'종목당 상한 {pos_cap:,.0f}원(한도/{POS_CAP_DIVISOR}), 최대 {BUY_SLOTS}종목')

    for k, cand in enumerate(live):
        if buys_today >= BUY_SLOTS:
            break
        stk_cd = cand['stk_cd']

        from auto_trading.kiwoom_api import get_current_price
        price = get_current_price(stk_cd)
        if price <= 0:
            continue

        # 남은 한도를 '남은 후보 수'로 재분할 → 비싸서 못 산 종목의 예산이 뒤 후보로 흘러간다.
        # 종목당 상한(pos_cap)과 한도 잔액으로 이중 제한.
        # 주의: get_current_price 실패로 skip된 종목은 분모에 남아 있어 예산이 약간 보수적으로
        #      계산된다(실패는 드물고, 과대 배정보다 안전한 방향이라 그대로 둔다).
        budget = (deploy_limit - deployed) / max(1, len(live) - k)
        spendable = min(budget, pos_cap, deploy_limit - deployed)
        qty = int(spendable // price)
        if qty <= 0:
            _log.info(f'[fire] {cand["stk_nm"]}({stk_cd}) 매수 예산 부족 '
                      f'(배정 예산 {spendable:,.0f}원 < 현재가 {price:,.0f}원)')
            continue

        trade_value = qty * price
        asset_ratio = (trade_value / summary['total_asset']) if summary['total_asset'] > 0 else 0.0

        ref = ''
        if cand['dist_20d_high'] is not None:
            ref = f'신고가대비 {cand["dist_20d_high"]:+.1f}%, 당일 {cand["ret_1d"]:+.1f}%, '
        result = buy_market(stk_cd, qty)
        if not order_accepted(result):
            # 주문 거부(장종료·NXT 미지원 등)는 체결이 아니므로 이력에 남기지 않고
            # deployed(한도 소진)에도 반영하지 않는다 — 반영하면 뒤 후보 예산이 잘못 줄어든다.
            _log.error(f'[fire매수-주문거부] {cand["stk_nm"]}({stk_cd}) 현재가={price:,}원 {qty}주 '
                       f'→ {result} (이력 미기록, 슬롯 미소진)')
            continue
        deployed += trade_value
        _log.info(f'[fire매수 {buys_today + 1}/{BUY_SLOTS}] {cand["stk_nm"]}({stk_cd}) 현재가={price:,}원 {qty}주 '
                  f'(총상승률 {cand["total_rate"]}, {ref}breadth={bd_txt}) '
                  f'거래대금={trade_value:,.0f}원(자산의 {asset_ratio:.1%}) '
                  f'누적 {deployed:,.0f}/{deploy_limit:,.0f}원 → {result}')
        _record_trade(stk_cd, cand['stk_nm'], 'buy', 'fire', qty, price, price, 0.0, asset_ratio=asset_ratio,
                      ord_no=result.get('ord_no'))

        state[stk_cd] = today.isoformat()
        buys_today += 1
        state['_daily'] = {'date': today.isoformat(), 'count': buys_today}
        _save_fire_state(state)


if __name__ == '__main__':
    import sys
    if '--check' in sys.argv:
        # 매수 없이 현재 레짐/후보만 확인
        b = get_market_breadth(force='--force' in sys.argv)
        print(f'시장폭: {b:.1%}' if b is not None else '시장폭 계산 실패',
              f'(레짐 {"ON" if b is not None and b >= BREADTH_MIN else "OFF"}, 기준 {BREADTH_MIN:.0%})')
        cands = get_fire_candidates(limit=CHECK_DISPLAY_LIMIT)
        try:
            from app.repository.stocks.stocks import get_reserved_stock_codes
            reserved = get_reserved_stock_codes()
        except Exception as e:
            reserved = set()
            print(f'  (reserved 목록 조회 실패: {e})')

        hit = [c for c in cands if c['stk_cd'] in reserved]
        print(f'fire 조건 통과 {len(cands)}건(최대 {CHECK_DISPLAY_LIMIT} 표시) / '
              f'reserved {len(reserved)}종목 → 매수 대상 {len(hit)}건 '
              f'(매수한도=가용현금의 {CASH_DEPLOY_RATIO:.0%}, '
              f'종목당 상한=한도/{POS_CAP_DIVISOR}, 최대 {BUY_SLOTS}종목)')
        for i, c in enumerate(cands, 1):
            ref = (f' 신고가대비 {c["dist_20d_high"]:+.1f}% 당일 {c["ret_1d"]:+.1f}%'
                   if c['dist_20d_high'] is not None else ' (pkl 오늘자 없음)')
            mark = '★매수대상' if c['stk_cd'] in reserved else '         '
            print(f'  {i:2d}. {mark} {c["stk_nm"]}({c["stk_cd"]}) 총상승률 {c["total_rate"]}{ref}')
    elif '--run' in sys.argv:
        if is_market_open():
            run_fire_buy_cycle()
        else:
            print('장 시간이 아님')
    else:
        print('사용법: python -m auto_trading.kiwoom_fire_strategy --check | --run')
