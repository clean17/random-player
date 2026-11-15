# -*- coding: utf-8 -*-
"""관심종목 추천 top N — 2026-09-08 추가, 2026-11-14 전면 재설계(v2).

■ v2 (2026-11-14) — "천천히 움직이기 시작한 종목"을 전 종목에서 찾는다
  흐름:
    1) 전 종목 피처 스냅샷(AutoSales.py/data/universe_snapshot.json)을 읽는다. 이 파일은
       AutoSales.py의 2_finding_stocks_with_increased_volume.py가 20분마다 전 종목 오늘 캔들을
       pkl에 반영하면서 같이 쓴다(universe_snapshot.py). 이 잡이 pkl을 직접 열지 않는 건
       safe_replace_pickle과의 파일 잠금 충돌(WinError 5) 때문이다.
    2) 유동성 유니버스(종가 1,000원↑, 20일 평균 거래대금 30억↑, 하루 약 650종목) 안에서
       피처마다 그날 백분위를 매기고, 아래 CONDITIONS의 '적정 구간'에 들면 1점씩(0~10점).
    3) 게이트: 오늘 등락 4~12%(2026-11-14 8→10→12) + 오늘/최근 10일 고저폭이 직전 ATR의 4배 미만(폭발 제외).
    4) 점수순(동점은 60일 고가 근접순) 상위 MAX_N, MIN_POINTS점 이상만.
    5) 그 종목들만 외국인/기관 순매수(ka10059)와 뉴스를 조회해 표시하고, 등급을 매긴다.
       외국인·기관이 둘 다 순매도면 등급을 '관심'으로 내린다.
    6) JSON 저장(logs/interest_stock_picks/<YYMM>/<DD>/picks_<YYYYMMDD_HHMM>.json + 바로 아래 latest.json,
       2026-11-14부터 월/일 폴더). 후보 상위
       CANDIDATE_LOG_N개의 피처·점수도 남긴다(사후 검증용).

  왜 바꿨나 — 9/8~11/13 15:20 추천 526건 사후 측정 + 2년 전 종목 재현(2024-09~2026-11):
    * 구 방식(등락률·거래대금 증가율 가점)은 2년 내내 졌다. 다음날 시가 진입 10일 기준 시장
      평균 대비 -3.2 / -3.1 / -2.5%p(24.9~25.8 / 25.9~26.8 / 26.9~), 하락(-7%↓) 확률이 기준의
      1.6~1.9배. 많이 오른 종목·거래대금이 폭증한 종목은 상승도 하락도 커지는 복권형이었다.
    * 후보 필터(조용하던 종목)는 처음 등록될 때만 적용되고 이후 종일 갱신돼, 라이브 후보의 82%가
      장 마감 기준으로는 필터를 통과하지 못했다(=사실상 '크게 튄 종목'을 고르고 있었다).
    * 1차 선별(등락률 60%)이 결과와 역상관(IC -0.13)이라, 그 뒤에 붙이는 수급 점수가 소용없었다.
      v2는 1차 선별과 최종 점수가 같은 점수다.
  v2 백테스트(같은 2년, 매일 상위 10, 다음날 시가 진입 10일, 비용 0.25% 차감 전 초과는 시장평균 대비):
                          상승(+7%↑)확률  하락(-7%↓)확률  초과수익
      24.9~25.8 (학습)      1.16배         0.98배       +0.76%p
      25.9~26.8 (검증)      1.23배         1.01배       +0.48%p
      26.9~11월 (검증)      1.16배         0.87배       +0.54%p
    구간 경계를 ±10%p 흔들어도 상승확률>1, 하락확률<1이 유지됐다(최근 구간 초과수익은 변형에 따라
    ±0.9%p로 흔들림). 점수별로 8~9점이 가장 좋고(초과 +1.0~+1.4%p) 4점 이하는 음수였다.
    수급(네이버, 7/9~11/12): 이 상위 10 안에서 기관 순매수 종목 초과 -0.37%p vs 순매도 -0.80%p,
    외국인·기관 둘 다 순매도 47건은 -3.11%p(상승확률 0.63배) — 그래서 점수엔 넣지 않고
    '둘 다 순매도' 강등만 한다.

  ⚠️ 한계
    * 검증은 '종가 신호 -> 다음날 시가 매수'로 했다. 장중(09:30~15:20) 결과는 그날 일부 데이터
      기준이라 검증되지 않은 근사다 — candidates 로그가 쌓이면 장중 vs 종가 신호를 비교할 것.
    * 2026-09 이후는 시장 자체가 크게 빠져서(10월 종목 중앙값 -15%) 절대수익은 음수였다.
      이 점수는 '시장보다 나은 종목'을 고르는 것이지 하락장을 피하는 장치가 아니다.
    * 피처 정의는 universe_snapshot.py와 백테스트가 같아야 한다. 구간을 바꾸면 재검증할 것.

⚠️ "얼마나 오를지" 확정 수치는 만들지 않는다 — 등급/상승여력은 점수 구간의 정성적 라벨이다.
"""
import os
import re
import json
import time
import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

from auto_trading.kiwoom_api import get_investor_trend, get_trading_logger, is_krx_business_day
from utils.request_toss_api import get_stock_news
# app.repository.stocks.stocks는 함수 안에서 지연 import한다(순환 import 방지) —
# job.batch_runner가 이 모듈을 최상단에서 import하는데, job.batch_runner는
# utils.common(run.py가 제일 먼저 import함)에서도 최상단에 import된다. 여기서
# app 패키지를 최상단에 import하면 app/__init__.py -> ... -> utils.common으로
# 다시 돌아오는 순환이 생겨 시작 자체가 깨진다(2026-09-08 실측: 서버가 아예 안 떴음).

_log = get_trading_logger('interest_stock_picks')

_OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'logs', 'interest_stock_picks')
SNAPSHOT_PATH = r'C:\my-project\AutoSales.py\data\universe_snapshot.json'
SNAPSHOT_MAX_AGE_MIN = 60   # 스냅샷이 이보다 오래되면(2_ 스크립트가 멈춤) 새 추천을 만들지 않는다

# 유니버스(백테스트와 동일)
UNIVERSE_MIN_CLOSE = 1000
UNIVERSE_MIN_AMT20 = 3_000_000_000

# 게이트
CHG_MIN, CHG_MAX = 4.0, 12.0  # 오늘 등락률 4% 이상 12% 미만.
# 2026-11-14 8 → 10 → 12 (사용자 요청). 근거(2년, 점수 상위10, 다음날 시가 기준 10일 시장 대비, 기간 P1/P2/P3):
#   8~10% 구간 단독 +1.26/+1.43/+0.13%p(상승확률 1.28~1.32배) / 10~12% +0.33/+0.05/+0.89%p(하락확률 1.16~1.39배)
#   슬롯 시뮬(10종목 10일, 종가 매수, 비용 0.25%) 월평균: 상한 8% +2.7% → 10% +3.4% → 12% +3.5% (손절 없음),
#   손절 -20%면 +2.0 → +2.4 → +2.8%(기간별 10%: +2.7/+4.0/-8.7, 12%: +2.5/+4.5/-6.2).
#   모의 손절 -20%와 짝으로 12% 채택. ⚠️ 10% 대비 우위는 대부분 최근(26.9~) 한 구간에서 나왔고,
#   10~12% 구간 단독은 하락확률 1.16~1.39배로 위험이 크다 — 모의 실측으로 10%와 다시 비교할 것.
#   12% 이상은 '이미 에너지를 쓴 종목(복권형)' 비중이 커진다.
EXPLODE_X = 4.0               # 오늘/최근 10일 고저폭이 직전 ATR14의 이 배수 이상이면 제외

# 적정 구간 조건 — (피처, 백분위 하한, 상한, 화면 설명). 구간은 24.9~25.8 데이터로만 정했다.
CONDITIONS: List[Tuple[str, float, float, str]] = [
    ('atr_n',    0.40, 0.80, '변동성 중간'),
    ('vr5_20',   0.50, 0.85, '단기 변동성 완만 확대'),
    ('vr20_60',  0.00, 0.60, '중기 변동성 아직 낮음'),
    ('tv5_20',   0.30, 0.85, '거래대금 완만 증가'),
    ('tvr',      0.40, 0.85, '오늘 거래대금 적당'),
    ('max_rx10', 0.00, 0.70, '최근 폭발 없음'),
    ('hi60',     0.60, 1.00, '60일 고가 근접'),
    ('upwick',   0.00, 0.60, '위꼬리 짧음'),
    ('spk20',    0.00, 0.70, '급등일 과다 아님'),
    ('ma60_gap', 0.00, 0.80, '60일선 과열 아님'),
]

MIN_POINTS = 5        # 이 점수 미만은 노출하지 않는다(4점 이하 상위10 편입분은 초과수익 음수)
MAX_N = 10            # 최종 노출 상한
CANDIDATE_LOG_N = 60  # 사후 검증용으로 남길 후보 수(게이트 통과자 점수순)
STRONG_POINTS = 8     # 적극매수 경계(8~9점 초과 +1.0~+1.4%p, 하락확률 0.88~0.91배)
BUY_POINTS = 6        # 매수 경계

# 2026-10-05: ka10059의 기관 순매수는 장중엔 일부 종목만 잠정치가 나오고 나머지는 0으로 온다.
# 추천 이력 실측(9/23~10/2) 기관=0 비율: 10시대 33~37%, 13시대 18~28%, 15시대 6~16%, 16시 이후 1%.
# 장 마감 후 값은 네이버 수급과 상관 1.0으로 일치 — 즉 장중 0은 '0원'이 아니라 '미집계'다.
# 이 시각 전의 기관 0은 None(미집계)으로 바꿔 '집계 전'으로 표시하고, 오늘 앞 사이클의 정상값이
# 있으면 그걸로 메운다(_carry_forward_flow).
INST_FINAL_HOUR = 16

# 2026-09-22: 외국인/기관 순매수 직전 정상값 캐시(종목코드 -> {'date','foreign','institution'}).
# ka10059가 간헐적으로(그 사이클에 조회된 종목 전부 동시에) 빈 값을 줄 때가 있는데
# (get_investor_trend() docstring의 실측 사례 참고), 그럴 때 0으로 표시하면 "갑자기 수급이
# 빠졌다"는 착각을 준다. 이번 사이클에 못 받은 필드만 직전 정상값으로 메운다.
# ⚠️ 프로세스 재시작하면 비워진다 — 의도적이다. 순매수는 그날 누적치라 날짜가 바뀌면
# 무의미해지므로, 캐시된 날짜가 오늘이 아니면 쓰지 않는다(아래 _carry_forward_flow).
_LAST_FLOW: Dict[str, Dict] = {}

def _carry_forward_flow(stk_cd: str, flow: Optional[Dict]) -> Optional[Dict]:
    """flow의 foreign/institution이 None(이번 사이클에 못 받음)이면 오늘자 직전 정상값으로
    채운다. 정상적으로 받은 필드는 캐시를 그 값으로 갱신한다."""
    if flow is None:
        return None
    today = datetime.date.today().isoformat()
    cached = _LAST_FLOW.get(stk_cd)
    cached = cached if (cached and cached.get('date') == today) else {'date': today}
    for key in ('foreign', 'institution'):
        if flow.get(key) is None:
            flow[key] = cached.get(key)   # 캐시에도 없으면(오늘 첫 조회) None 그대로 — '-' 표시
        else:
            cached[key] = flow[key]
    cached['date'] = today
    _LAST_FLOW[stk_cd] = cached
    return flow


def _load_snapshot() -> Optional[Dict]:
    """스냅샷 JSON을 읽는다. 쓰는 쪽(os.replace)과 겹치면 PermissionError가 날 수 있어 짧게 재시도."""
    for attempt in range(3):
        try:
            with open(SNAPSHOT_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return None
        except (PermissionError, json.JSONDecodeError):
            time.sleep(0.5 * (attempt + 1))
    return None


def score_universe(rows: List[Dict], today_iso: str) -> pd.DataFrame:
    """스냅샷 행 -> 오늘자 유동성 유니버스 + 백분위/점수/게이트 컬럼이 붙은 DataFrame."""
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df[(df['date'] == today_iso)
            & (df['close'] >= UNIVERSE_MIN_CLOSE)
            & (df['amt20'] >= UNIVERSE_MIN_AMT20)].copy()
    if df.empty:
        return df
    df['points'] = 0
    met = []
    for feat, lo, hi, _desc in CONDITIONS:
        pct = df[feat].rank(pct=True)
        ok = (pct >= lo) & (pct <= hi)
        df['points'] += ok.astype(int)
        met.append(ok.rename(feat))
    df['met'] = pd.concat(met, axis=1).apply(lambda r: [f for f, v in r.items() if v], axis=1)
    df['hi60_pct'] = df['hi60'].rank(pct=True)
    df['gate'] = ((df['chg'] >= CHG_MIN) & (df['chg'] < CHG_MAX)
                  & (df['rng_x'] < EXPLODE_X) & (df['max_rx10'] < EXPLODE_X))
    df['rank_key'] = df['points'] + df['hi60_pct'] * 0.01   # 동점은 60일 고가 근접순(백테스트와 동일)
    return df


def _label(points: int, both_selling: bool) -> Tuple[str, Optional[str]]:
    """(등급, 화면 툴팁용 메모). 외국인·기관 둘 다 순매도면 '관심'으로 내린다."""
    base = '적극매수' if points >= STRONG_POINTS else ('매수' if points >= BUY_POINTS else '관심')
    if both_selling and base != '관심':
        return '관심', '점수는 %s 구간이지만 외국인·기관이 모두 순매도라 관심으로 표시' % base
    return base, None


def _upside_tier(label: str) -> str:
    # 등급과 어긋나지 않게 등급에서 파생한다
    if label == '적극매수':
        return '상승여력 높음'
    if label == '매수':
        return '상승여력 보통'
    return '상승여력 낮음'


_DESC = {feat: desc for feat, _lo, _hi, desc in CONDITIONS}


def _num(v, nd: Optional[int] = None):
    """NaN/inf/None -> None (json.dump가 NaN을 그대로 써서 브라우저 JSON 파싱이 깨지는 것 방지)."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x or x in (float('inf'), float('-inf')):
        return None
    return round(x, nd) if nd is not None else x


def generate_picks(max_n: int = MAX_N) -> Optional[Dict]:
    from app.repository.stocks.stocks import get_logo_urls_by_codes  # 지연 import(위 주석 참고)

    started = time.perf_counter()
    snap = _load_snapshot()
    if not snap:
        _log.error('관심종목 추천: 전 종목 스냅샷 없음(%s) — 2_finding 스크립트가 아직 안 돌았거나 실패', SNAPSHOT_PATH)
        return None
    snap_at = datetime.datetime.fromisoformat(snap['generated_at'])
    age_min = (datetime.datetime.now() - snap_at).total_seconds() / 60
    if age_min > SNAPSHOT_MAX_AGE_MIN:
        _log.error('관심종목 추천: 스냅샷이 %.0f분 묵음(생성 %s) — 새 추천을 만들지 않는다', age_min, snap['generated_at'])
        return None

    today_iso = datetime.date.today().isoformat()
    uni = score_universe(snap.get('rows') or [], today_iso)
    if uni.empty:
        _log.error('관심종목 추천: 오늘자(%s) 유니버스가 비었음 — 스냅샷 %d행', today_iso, snap.get('count', 0))
        return None

    gated = uni[uni['gate']].sort_values('rank_key', ascending=False)
    qualified = gated[gated['points'] >= MIN_POINTS]
    top = qualified.head(max_n)

    inst_pending_window = datetime.datetime.now().hour < INST_FINAL_HOUR
    codes = top['code'].tolist()
    logos = get_logo_urls_by_codes(codes) if codes else {}

    picks = []
    for r in top.itertuples():
        flow = get_investor_trend(r.code, env='real')
        if flow is not None and inst_pending_window and flow.get('institution') == 0:
            flow['institution'] = None   # 장중 0 = 미집계 (INST_FINAL_HOUR 주석 참고)
        flow = _carry_forward_flow(r.code, flow)
        f_net = flow.get('foreign') if flow else None
        i_net = flow.get('institution') if flow else None
        both_selling = f_net is not None and i_net is not None and f_net < 0 and i_net < 0
        label, note = _label(int(r.points), both_selling)
        today_tv = _num(r.today_tv)
        flow_ratio = None
        if flow and today_tv and today_tv > 0:
            flow_ratio = _num(((f_net or 0) + (i_net or 0)) / today_tv, 4)
        tvr = _num(r.tvr)
        picks.append({
            'stock_code': r.code,
            'stock_name': r.name,
            'logo_url': logos.get(r.code),
            'today_price_change_pct': _num(r.chg, 2),
            'trading_value_change_pct': round(tvr * 100, 2) if tvr is not None else None,
            'current_trading_value': today_tv,
            'current_price': _num(r.close),
            'foreign_net': f_net,
            'institution_net': i_net,
            # 장중 기관 미집계(화면에 '집계 전'). 조회 실패(flow None)와 구분한다
            'institution_pending': bool(flow and i_net is None and inst_pending_window),
            'flow_ratio': flow_ratio,
            'points': int(r.points),
            'score': round(int(r.points) / len(CONDITIONS), 2),
            'score_detail': '충족: ' + ', '.join(_DESC[f] for f in r.met) + ' / 미충족: '
                            + ', '.join(desc for f, desc in _DESC.items() if f not in r.met),
            'label': label,
            'label_note': note,
            'upside_tier': _upside_tier(label),
            'news': get_stock_news(r.name, limit=3),
        })

    picked = set(codes)
    feat_cols = ['chg', 'tvr', 'tv5_20', 'atr_n', 'rng_x', 'vr5_20', 'vr20_60', 'max_rx10', 'hi60', 'upwick', 'spk20', 'ma60_gap']
    candidates_log = []
    for r in gated.head(CANDIDATE_LOG_N).itertuples():
        item = {'stock_code': r.code, 'stock_name': r.name, 'current_price': _num(r.close),
                'points': int(r.points), 'picked': r.code in picked}
        for c in feat_cols:
            item[c] = _num(getattr(r, c), 4)
        candidates_log.append(item)

    now = datetime.datetime.now()
    result = {
        'generated_at': now.isoformat(timespec='seconds'),
        'scheme': 'v2',
        'snapshot_at': snap['generated_at'],
        'candidate_count': int(len(uni)),          # 오늘 유동성 유니버스 크기
        'prescreened_count': int(len(gated)),      # 게이트(등락 4~12%, 폭발 제외) 통과 수
        'picks': picks,
        'candidates': candidates_log,              # 사후 검증용(화면 미사용)
        'disclaimer': '전 종목 중 "조용하던 종목이 완만하게 움직이기 시작한" 패턴을 점수화한 참고용 순위입니다 '
                      '(백테스트는 장 마감 신호 → 다음날 시가 매수 기준, 장중 결과는 그날 일부 데이터 기준). '
                      '실제 매수 여부와 손익 책임은 본인에게 있습니다.',
    }

    day_dir = picks_day_dir(now.strftime('%Y%m%d'))
    os.makedirs(day_dir, exist_ok=True)
    ts = now.strftime('%Y%m%d_%H%M')
    with open(os.path.join(day_dir, f'picks_{ts}.json'), 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open(os.path.join(_OUT_DIR, 'latest.json'), 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    _log.info('관심종목 추천(v2) 생성: 유니버스 %d -> 게이트 %d -> %d점↑ %d -> 최종 %d건 '
              '(스냅샷 %s, %.0f분 전, 소요 %.1f초)',
              len(uni), len(gated), MIN_POINTS, len(qualified), len(picks),
              snap['generated_at'], age_min, time.perf_counter() - started)
    return result


def log_config():
    """서버 시작 시 실제 적용 값을 한 줄로 남긴다(재시작 후 새 값 반영 확인용)."""
    _log.info('[config] interest_stock_picks v2: 등락 %.0f~%.0f%%, 폭발 %.0f배 미만, 유니버스 종가 %d↑ 20일거래대금 %.0f억↑, '
              '점수 %d점↑ 상위 %d, 적극매수 %d점↑/매수 %d점↑, 조건=%s',
              CHG_MIN, CHG_MAX, EXPLODE_X, UNIVERSE_MIN_CLOSE, UNIVERSE_MIN_AMT20 / 1e8,
              MIN_POINTS, MAX_N, STRONG_POINTS, BUY_POINTS,
              ','.join('%s[%.2f-%.2f]' % (f, lo, hi) for f, lo, hi, _ in CONDITIONS))


def run_interest_stock_picks():
    """스케줄러 등록용 래퍼 — 예외를 삼켜서 스케줄 전체가 죽지 않게 한다.
    ⚠️ 2026-09-24: 공휴일엔 원천 데이터가 전날 것 그대로라 5분마다 돌려봐야 결과가 똑같고,
    외국인/기관 순매수(ka10059) 조회까지 나가 API를 낭비한다 — is_krx_business_day()로 건너뛴다."""
    if not is_krx_business_day():
        return
    try:
        generate_picks()
    except Exception as e:
        _log.error('관심종목 추천 생성 실패: %s', e)


def load_latest_picks() -> Optional[Dict]:
    path = os.path.join(_OUT_DIR, 'latest.json')
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        _log.error('관심종목 추천 로드 실패: %s', e)
        return None


def picks_day_dir(date_str: str) -> str:
    """YYYYMMDD -> logs/interest_stock_picks/<YYMM>/<DD> (2026-11-14 사용자 요청, 예: 2611/08).
    latest.json만 _OUT_DIR 바로 아래에 둔다. kiwoom_fire_strategy_mock._load_today_picks도 이 경로를 쓴다."""
    return os.path.join(_OUT_DIR, date_str[2:6], date_str[6:8])


def list_picks_files(date_str: str) -> List[str]:
    """그날 picks_<YYYYMMDD>_HHMM.json 전체 경로, 시간순. 새 구조(<YYMM>/<DD>/)에 없으면 예전
    평면 구조(_OUT_DIR 바로 아래)도 본다 — 2026-11-14 이전 파일 이전이 실패했을 때 대비."""
    prefix = f'picks_{date_str}_'
    for d in (picks_day_dir(date_str), _OUT_DIR):
        try:
            files = sorted(f for f in os.listdir(d) if f.startswith(prefix) and f.endswith('.json'))
        except OSError:
            continue
        if files:
            return [os.path.join(d, f) for f in files]   # 파일명이 picks_YYYYMMDD_HHMM.json이라 정렬 = 시간순
    return []


def load_picks_for_date(date_str: str) -> Optional[Dict]:
    """특정 날짜(YYYYMMDD)에 생성된 추천 중 가장 마지막(최신) 결과를 반환한다.

    generate_picks()가 실행마다 latest.json과 별도로 picks_<YYYYMMDD_HHMM>.json도 남겨두므로
    (평일 09:30~20:00 5분마다), 화면에서 과거 날짜를 골랐을 때도 그날 마지막 생성분을 그대로
    다시 보여줄 수 있다 — 2026-09-21 날짜 검색 기능 추가. 그날 파일이 하나도 없으면 None."""
    if not date_str or not re.fullmatch(r'\d{8}', date_str):
        return None
    files = list_picks_files(date_str)
    if not files:
        return None
    path = files[-1]
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        _log.error('관심종목 추천 로드 실패(%s): %s', date_str, e)
        return None
