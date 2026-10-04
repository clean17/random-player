# -*- coding: utf-8 -*-
"""관심종목(interest_stocks) 중 추천 top N — 2026-09-08 추가.

규칙 기반 점수/라벨 방식(사용자 선택, LLM 서술형 아님). 흐름:
  1) 오늘자 관심종목 후보 조회 (app.repository.stocks.stocks.get_interest_stocks)
  2) 이미 있는 값(등락률/거래대금 증가율)만으로 1차 예선 -> PRESCREEN_N개로 추림
     (외국인/기관 조회는 종목당 API 호출이 들어서, 전체 후보 전부에 안 하고 예선 통과자만)
  3) 예선 통과자에 한해 외국인/기관 순매수(ka10059)를 조회해 최종 점수 계산
  4) 최종 점수가 MIN_SCORE(='관심' 등급 경계) 이상인 것만, 최대 MAX_N개까지 뉴스(Toss NEWS
     섹션)까지 조회해서 리포트에 포함 — 2026-09-22부터 고정 10개가 아니라 이 기준으로 개수가
     날마다 변한다(임계값 미만이면 0개일 수도, 상한까지 15개일 수도 있음). 무조건 10개를
     채우다 보니 약세장엔 '관망'급까지 억지로 노출되고 강세장엔 11~15위 유망 종목이 잘리던
     문제 대응.
  5) JSON으로 저장 (logs/interest_stock_picks/picks_<타임스탬프>.json, latest.json)
     2026-10-05부터 최종 picks 외에 후보 전체(candidates)와 예선 통과자의 수급·최종점수
     (prescreened)도 같이 남긴다 — 사후 검증용. 전엔 picks만 남아 탈락 후보의 장중 값과
     수급이 사라져서, '점수식이 후보 중에서 잘 골랐는가'를 실제 추천 시점 데이터로 잴 수
     없었다(그날 최종값은 DB에 있지만 장중 스냅샷과 수급은 없음). 추가 API 호출은 없다.

⚠️ "얼마나 오를지"는 백테스트/모델 근거가 없어 확정 수치를 만들지 않는다 — 점수 구간에 따른
   정성적 라벨(상승여력 높음/보통/낮음)만 준다. 실제 매수 여부는 사용자 판단이다.
"""
import os
import re
import json
import datetime
from typing import Dict, List, Optional

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

PRESCREEN_N = 20   # 외국인/기관 조회(API 호출)까지 갈 예선 통과 수
MIN_SCORE = 0.40   # 최종 노출 최소 점수 = _label()의 '관심' 등급 경계. 미만('관망')은 아예 안 보여준다.
MAX_N = 15         # 최종 노출 상한(임계값을 넘는 종목이 많아도 여기서 자른다)

# 2026-10-05: '적극매수'는 점수 0.70 이상 + 외국인·기관 순매수 합이 거래대금의 이 비율 이상일 때만.
# 미달이면 '매수'로 한 단계 내린다(점수·정렬·자동매수 대상 여부는 그대로 — 매수/적극매수 둘 다 대상).
# 근거(9/8~10/2 15:20 추천 실측): 등급별 D+1/D+3/D+5가 관심 +1.1/+5.4/+8.1%,
# 매수 +0.9/+2.4/+4.7%, 적극매수 -0.1/+0.4/+3.4%로 점수가 높을수록 오히려 나빴다. 등락률 30%·
# 거래대금 5배를 채우면 수급이 0이어도 0.60+0.20(수급 중립)=0.80이 돼서, 수급 없는 상한가 종목이
# 최고 등급을 받던 구조다. 적극매수 중 수급 3% 이상 44건은 D+3 +1.5%(승률 57%), 미만 22건은
# -1.7%(41%). 네이버 수급(7~10월, 39거래일)에서도 당일 외+기 순매수 비중은 넓은 후보군 기준
# 양(+)의 신호였다(IC +0.07, t 2.7). 표본이 작아 확정치는 아니다 — candidates 기록이 쌓이면 재검증.
STRONG_FLOW_MIN = 0.03

# 2026-10-05: ka10059의 기관 순매수는 장중엔 일부 종목만 잠정치가 나오고 나머지는 0으로 온다.
# 추천 이력 실측(9/23~10/2) 기관=0 비율: 10시대 33~37%, 13시대 18~28%, 15시대 6~16%, 16시 이후 1%.
# 장 마감 후 값은 네이버 수급과 상관 1.0으로 일치 — 즉 장중 0은 '0원'이 아니라 '미집계'다.
# 이 시각 전의 기관 0은 None(미집계)으로 바꿔 '집계 전'으로 표시하고, 오늘 앞 사이클의 정상값이
# 있으면 그걸로 메운다(_carry_forward_flow). 점수 계산에선 None=0이라 기존과 같다.
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


def _f(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _prescreen_score(row: Dict) -> float:
    """1차 예선 점수 — API 호출 없이 이미 가진 값만으로."""
    chg = min(_f(row.get('today_price_change_pct')), 30.0) / 30.0        # 등락률, 30%에서 캡
    vol = min(_f(row.get('trading_value_change_pct')), 500.0) / 500.0    # 거래대금 증가율, 500%에서 캡
    return chg * 0.6 + vol * 0.4


def _final_score(row: Dict, flow: Optional[Dict]) -> float:
    chg = min(_f(row.get('today_price_change_pct')), 30.0) / 30.0
    vol = min(_f(row.get('trading_value_change_pct')), 500.0) / 500.0
    trd_amt = _f(row.get('last_trading_value'))
    flow_score = 0.5   # 외국인/기관 조회 실패·데이터 없음 = 중립
    if flow and trd_amt > 0:
        net = _f(flow.get('foreign')) + _f(flow.get('institution'))
        ratio = net / trd_amt   # 오늘 거래대금 대비 외국인+기관 순매수 비중
        # -10%~+10%를 0~1로 매핑(그 밖은 클램프) — 임의 스케일, 근거는 없고 상대비교용
        flow_score = max(0.0, min(1.0, 0.5 + ratio * 5))
    return chg * 0.35 + vol * 0.25 + flow_score * 0.40


def _flow_ratio(row: Dict, flow: Optional[Dict]) -> Optional[float]:
    """외국인+기관 순매수 / 오늘 거래대금. 수급 조회 실패나 거래대금 0이면 None."""
    trd_amt = _f(row.get('last_trading_value'))
    if not flow or trd_amt <= 0:
        return None
    return (_f(flow.get('foreign')) + _f(flow.get('institution'))) / trd_amt


def _label(score: float, flow_ratio: Optional[float] = None) -> str:
    if score >= 0.70:
        # 수급 확인이 안 되면(조회 실패 포함) 적극매수를 주지 않는다 — STRONG_FLOW_MIN 주석 참고
        return '적극매수' if (flow_ratio is not None and flow_ratio >= STRONG_FLOW_MIN) else '매수'
    if score >= 0.55:
        return '매수'
    if score >= 0.40:
        return '관심'
    return '관망'


def _upside_tier(label: str) -> str:
    # 등급과 어긋나지 않게 등급에서 파생한다(적극매수에서 내려간 종목이 '높음'으로 남지 않도록)
    if label == '적극매수':
        return '상승여력 높음'
    if label == '매수':
        return '상승여력 보통'
    return '상승여력 낮음'


def generate_picks(min_score: float = MIN_SCORE, max_n: int = MAX_N) -> Dict:
    from app.repository.stocks.stocks import get_interest_stocks  # 지연 import(위 주석 참고)

    today = datetime.date.today().strftime('%Y%m%d')
    rows = get_interest_stocks(today, today, mode='normal', target_value='interest')

    # 같은 종목이 하루에 여러 번 갱신될 수 있어(등락률 재조회 등) 코드별 최신 1건만 남긴다
    latest_by_code: Dict[str, Dict] = {}
    for row in rows:
        code = row['stock_code']
        prev = latest_by_code.get(code)
        if prev is None or row['created_at'] > prev['created_at']:
            latest_by_code[code] = row
    candidates = list(latest_by_code.values())

    prescreened = sorted(candidates, key=_prescreen_score, reverse=True)[:PRESCREEN_N]

    inst_pending_window = datetime.datetime.now().hour < INST_FINAL_HOUR
    enriched = []
    for row in prescreened:
        flow = get_investor_trend(row['stock_code'], env='real')
        if flow is not None and inst_pending_window and flow.get('institution') == 0:
            flow['institution'] = None   # 장중 0 = 미집계 (INST_FINAL_HOUR 주석 참고)
        flow = _carry_forward_flow(row['stock_code'], flow)
        score = _final_score(row, flow)
        enriched.append((row, flow, score))

    qualified = sorted((t for t in enriched if t[2] >= min_score), key=lambda t: t[2], reverse=True)
    top = qualified[:max_n]

    picks = []
    for row, flow, score in top:
        news = get_stock_news(row['stock_name'], limit=3)
        ratio = _flow_ratio(row, flow)
        label = _label(score, ratio)
        picks.append({
            'stock_code': row['stock_code'],
            'stock_name': row['stock_name'],
            'logo_url': row.get('logo_image_url'),
            'today_price_change_pct': _f(row.get('today_price_change_pct')),
            'trading_value_change_pct': _f(row.get('trading_value_change_pct')),
            'current_trading_value': _f(row.get('last_trading_value')),
            'current_price': _f(row.get('current_price')),
            'foreign_net': flow.get('foreign') if flow else None,
            'institution_net': flow.get('institution') if flow else None,
            # 장중 기관 미집계(화면에 '집계 전'). 조회 실패(flow None)와 구분한다
            'institution_pending': bool(flow and flow.get('institution') is None and inst_pending_window),
            'flow_ratio': round(ratio, 4) if ratio is not None else None,
            'score': round(score, 3),
            'label': label,
            'upside_tier': _upside_tier(label),
            'news': news,
        })

    picked_codes = {p['stock_code'] for p in picks}
    flow_by_code = {row['stock_code']: (flow, score) for row, flow, score in enriched}
    candidates_log = []
    for row in sorted(candidates, key=_prescreen_score, reverse=True):
        code = row['stock_code']
        item = {
            'stock_code': code,
            'stock_name': row['stock_name'],
            'today_price_change_pct': _f(row.get('today_price_change_pct')),
            'trading_value_change_pct': _f(row.get('trading_value_change_pct')),
            'current_trading_value': _f(row.get('last_trading_value')),
            'current_price': _f(row.get('current_price')),
            'prescreen_score': round(_prescreen_score(row), 4),
            'created_at': str(row.get('created_at')),
            'picked': code in picked_codes,
        }
        if code in flow_by_code:   # 예선 통과자만 수급·최종점수가 있다
            flow, score = flow_by_code[code]
            item['foreign_net'] = flow.get('foreign') if flow else None
            item['institution_net'] = flow.get('institution') if flow else None
            item['institution_pending'] = bool(flow and flow.get('institution') is None and inst_pending_window)
            item['final_score'] = round(score, 4)
        candidates_log.append(item)

    result = {
        'generated_at': datetime.datetime.now().isoformat(timespec='seconds'),
        'candidate_count': len(candidates),
        'prescreened_count': len(prescreened),
        'picks': picks,
        'candidates': candidates_log,   # 사후 검증용(화면 미사용). 위 docstring 5) 참고
        'disclaimer': '정량 지표(등락률·거래대금 증가율·외국인/기관 순매수) 기반 참고용 순위입니다. '
                      '실제 매수 여부와 손익 책임은 본인에게 있습니다.',
    }

    os.makedirs(_OUT_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M')
    with open(os.path.join(_OUT_DIR, f'picks_{ts}.json'), 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open(os.path.join(_OUT_DIR, 'latest.json'), 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    _log.info('관심종목 추천 생성: 후보 %d건 -> 예선 %d건 -> 점수 %.2f 이상 %d건(상한 %d건) -> 최종 %d건',
              len(candidates), len(prescreened), min_score, len(qualified), max_n, len(picks))
    return result


def run_interest_stock_picks():
    """스케줄러 등록용 래퍼 — 예외를 삼켜서 스케줄 전체가 죽지 않게 한다.
    ⚠️ 2026-09-24: 공휴일엔 등락률/거래대금 등 원천 데이터가 전날 것 그대로라 5분마다
    돌려봐야 결과가 똑같고, 예선 통과자가 있으면 외국인/기관 순매수(ka10059) 조회까지
    나가 API를 낭비한다 — is_krx_business_day()로 건너뛴다."""
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


def load_picks_for_date(date_str: str) -> Optional[Dict]:
    """특정 날짜(YYYYMMDD)에 생성된 추천 중 가장 마지막(최신) 결과를 반환한다.

    generate_picks()가 실행마다 latest.json과 별도로 picks_<YYYYMMDD_HHMM>.json도 남겨두므로
    (평일 09:30~20:00 5분마다), 화면에서 과거 날짜를 골랐을 때도 그날 마지막 생성분을 그대로
    다시 보여줄 수 있다 — 2026-09-21 날짜 검색 기능 추가. 그날 파일이 하나도 없으면 None."""
    if not date_str or not re.fullmatch(r'\d{8}', date_str):
        return None
    prefix = f'picks_{date_str}_'
    try:
        files = sorted(f for f in os.listdir(_OUT_DIR) if f.startswith(prefix) and f.endswith('.json'))
    except OSError:
        return None
    if not files:
        return None
    path = os.path.join(_OUT_DIR, files[-1])  # 파일명이 picks_YYYYMMDD_HHMM.json이라 정렬 = 시간순
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        _log.error('관심종목 추천 로드 실패(%s): %s', date_str, e)
        return None
