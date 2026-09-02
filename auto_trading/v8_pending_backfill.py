# -*- coding: utf-8 -*-
"""v8 pending 상태(kiwoom_v8_pending_*.json) 재해복구용 백필. (Python 3.8)

배경: 2026-08-26 10:15 kiwoom_v8_pending_real.json 이 동시쓰기 충돌([WinError 32])로
깨져 pending/ordered 가 전부 날아갔다(kiwoom_v8_strategy.py:184-196 주석 참고, 이미 고쳐짐 —
_pending_lock + pid/thread별 임시파일명). 그날 아침 pkl을 이용해 과거 여러 거래일을
재현해서 즉시 정상 깊이(age 0~10)로 복구했었다.

이 스크립트는 그 복구 방식을 정식화한다:
  1) 유동성 큰 종목(기본 005930)의 pkl 날짜를 KRX 거래일 달력으로 삼는다.
  2) `run_v8_screen()` 이 매일 15:55 로 했을 일을, 과거 각 거래일 "그날 종가까지만
     보이는 pkl" 로 하루씩 재생(replay)한다 — 실제 screen_today()/merge 로직을
     그대로 재사용한다(로직이 바뀌면 이 스크립트도 자동으로 같이 바뀐다).
  3) 재생 결과를 실제 pending 파일과 비교(--verify)하거나, 실제 파일에 반영한다(--apply).

⚠️ --apply 는 라이브 v8 상태 파일을 덮어쓴다. 반드시 --verify로 먼저 차이를 확인하고,
   실제 사고 복구 상황이 아니면 쓰지 말 것. 스케줄러(run.py) 가동 중엔 서로 다른 프로세스가
   같은 파일을 동시에 쓰지 않도록 확인 후 실행할 것.

사용:
  venv/Scripts/python.exe -m auto_trading.v8_pending_backfill --verify
  venv/Scripts/python.exe -m auto_trading.v8_pending_backfill --verify --days 15
  venv/Scripts/python.exe -m auto_trading.v8_pending_backfill --apply --env real   # 실제 복구 시에만
"""
import os
import sys
import copy
import argparse
import datetime
from typing import Dict, List, Optional

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from auto_trading import kiwoom_v8_strategy as v8  # noqa: E402
from auto_trading.kiwoom_api import env_path  # noqa: E402

# run_v8_screen() 의 유효기간+2 상한과 동일 — 이 스크립트만의 독립 상수가 아니라 그쪽을 따라간다.
_CAP = v8.VALID_DAYS + 2
# 트레이딩 캘린더 추출용 기준 종목 — 유동성이 커서 결측/거래정지가 사실상 없다고 가정.
_CALENDAR_REF_CODE = '005930'


def _trading_calendar(end_date: Optional[datetime.date] = None, back_days: int = 20) -> List[datetime.date]:
    """기준 종목의 pkl 날짜를 KRX 거래일 달력으로 쓴다. end_date 이하만, 최근 back_days개."""
    d = v8._load_daily(_CALENDAR_REF_CODE)
    if d is None:
        raise RuntimeError(f'{_CALENDAR_REF_CODE}.pkl 을 못 읽었다 — 기준 종목을 바꿔서 재시도할 것')
    dates = [ts.date() for ts in d.index]
    if end_date is not None:
        dates = [x for x in dates if x <= end_date]
    return dates[-back_days:]


def _screen_asof(as_of: datetime.date, full_cache: Dict[str, Optional[pd.DataFrame]]) -> List[Dict]:
    """screen_today() 를 as_of 날짜까지만 보이는 pkl로 실행 — 실제 함수를 그대로 재사용한다.

    v8._load_daily 를 그 순간만 '캐시에서 as_of 이하로 자른 뷰'를 돌려주는 함수로 바꿔치기한다.
    풀 pkl은 한 번만 읽고(full_cache) 잘라내기만 반복하므로, 거래일 수만큼 늘어나도
    디스크 I/O는 늘지 않는다.
    """
    as_of_ts = pd.Timestamp(as_of)

    def _truncated_loader(code: str) -> Optional[pd.DataFrame]:
        if code not in full_cache:
            full_cache[code] = _orig_load_daily(code)
        d = full_cache[code]
        if d is None:
            return None
        d2 = d[d.index <= as_of_ts]
        # _load_daily() 자신도 80행 미만이면 None을 돌려준다 — 잘라낸 뒤에도 같은 기준을 적용.
        return d2 if len(d2) >= 80 else None

    def _data_stale_asof(d: pd.DataFrame, max_days: int = v8.STALE_MAX_DAYS) -> bool:
        # v8._data_stale() 원본은 datetime.date.today()(진짜 오늘)와 비교한다 — 과거 as_of
        # 날짜를 재생할 때 그대로 쓰면 5일보다 오래된 모든 날짜가 전부 '오래됨'으로 걸려
        # 스크리닝 적중이 0건이 된다(실측: 2026-08-27 기준 08-21 이전 전부 0건 — 이 버그였다).
        if d is None or len(d) == 0:
            return True
        return (as_of - d.index[-1].date()).days > max_days

    _orig_load_daily = v8._load_daily
    _orig_data_stale = v8._data_stale
    v8._load_daily = _truncated_loader
    v8._data_stale = _data_stale_asof
    try:
        return v8.screen_today()
    finally:
        v8._load_daily = _orig_load_daily
        v8._data_stale = _orig_data_stale


def _merge_one_day(pend: Dict[str, Dict], hits: List[Dict]) -> int:
    """run_v8_screen() 의 병합 로직(만료 age+1 → 유니버스밖 제거 → 오늘자 hits 추가/갱신)을
    독립 상태 dict에 대해 그대로 재현한다. 실제 함수(kiwoom_v8_strategy.run_v8_screen)와
    로직이 갈라지지 않도록, 그 함수를 고칠 때 이 함수도 같이 봐야 한다.
    """
    uni = v8.universe_codes()
    for code in list(pend):
        bad = (code not in uni) if uni is not None else \
            (not (len(code) == 6 and code.isdigit() and code[-1] == '0'))
        if bad:
            del pend[code]
            continue
        vv = v8._migrate(pend[code])
        for e in vv['limits']:
            e['age'] = e.get('age', 0) + 1
        vv['limits'] = [e for e in vv['limits'] if e.get('age', 0) <= v8.VALID_DAYS]
        if not vv['limits']:
            del pend[code]
        else:
            pend[code] = vv

    added = 0
    for s in hits:
        code = s['code']
        lim = int(s['limit'])
        cur = v8._migrate(pend[code]) if code in pend else None
        entry = {'limit': lim, 'age': 0, 'sig_date': s['sig_date'], 'sig_close': s['sig_close']}
        if cur is None:
            s = dict(s)
            s.pop('limit', None)
            s['limits'] = [entry]
            pend[code] = s
            added += 1
        else:
            same = [e for e in cur['limits'] if int(e['limit']) == lim]
            if same:
                for e in same:
                    e['age'] = 0
            else:
                cur['limits'].append(entry)
                added += 1
            for k in ('atr', 'ma20', 'amount', 'drop5', 'sig_close', 'sig_date'):
                if k in s:
                    cur[k] = s[k]
            if len(cur['limits']) > _CAP:
                cur['limits'] = sorted(cur['limits'], key=lambda e: e.get('age', 0))[:_CAP]
            pend[code] = cur
    return added


def replay(end_date: Optional[datetime.date] = None, back_days: int = 20) -> Dict:
    """end_date(기본 오늘)까지, back_days 거래일을 하루씩 재생해 pending 을 재구성한다."""
    if end_date is None:
        end_date = datetime.date.today()
    calendar = _trading_calendar(end_date, back_days)
    if not calendar:
        raise RuntimeError('거래일 달력을 못 만들었다')

    full_cache: Dict[str, Optional[pd.DataFrame]] = {}
    pend: Dict[str, Dict] = {}
    log = []
    for d in calendar:
        hits = _screen_asof(d, full_cache)
        added = _merge_one_day(pend, hits)
        log.append((d, len(hits), added, len(pend)))
    return {'pending': pend, 'calendar': calendar, 'log': log}


def _limit_set(v: Dict) -> set:
    return {(int(e['limit']), int(e.get('age', 0))) for e in v8._migrate(v)['limits']}


def compare(sim_pend: Dict[str, Dict], real_pend: Dict[str, Dict]) -> Dict:
    sim_codes = set(sim_pend)
    real_codes = set(real_pend)
    only_sim = sim_codes - real_codes
    only_real = real_codes - sim_codes
    common = sim_codes & real_codes
    mismatched = {}
    for code in common:
        a, b = _limit_set(sim_pend[code]), _limit_set(real_pend[code])
        if a != b:
            mismatched[code] = {'sim_only': sorted(a - b), 'real_only': sorted(b - a)}
    return {
        'sim_total': len(sim_codes), 'real_total': len(real_codes),
        'only_in_sim': sorted(only_sim), 'only_in_real': sorted(only_real),
        'common': len(common), 'exact_match_common': len(common) - len(mismatched),
        'mismatched': mismatched,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--verify', action='store_true', help='재생 결과를 실제 pending과 비교만 한다(쓰기 없음)')
    ap.add_argument('--apply', action='store_true', help='⚠️ 재생 결과를 실제 pending 파일에 반영한다')
    ap.add_argument('--env', default=None, help='real|mock (기본: 프로세스 KIWOOM_ENV)')
    ap.add_argument('--days', type=int, default=20, help='재생할 거래일 수(기본 20 — VALID_DAYS+2 스팟보다 넉넉히)')
    ap.add_argument('--end-date', default=None, help='YYYY-MM-DD (기본 오늘)')
    args = ap.parse_args()

    if not args.verify and not args.apply:
        args.verify = True  # 기본은 안전한 검증 모드

    end_date = (datetime.date.fromisoformat(args.end_date) if args.end_date
                else datetime.date.today())

    print(f'재생 기준일: {end_date} / 최근 {args.days}거래일')
    result = replay(end_date, args.days)
    sim_pend = result['pending']

    print('\n[일자별 재생 로그]  날짜        스크리닝적중  신규/갱신  누적종목수')
    for d, hits, added, total in result['log']:
        print(f'  {d}   {hits:>6}건        {added:>5}건      {total:>6}건')

    state_path = env_path(os.path.join(os.path.dirname(__file__), 'kiwoom_v8_pending.json'), args.env)
    with open(state_path, 'r', encoding='utf-8') as f:
        real_state = __import__('json').load(f)
    real_pend = real_state.get('pending', {})

    cmp_result = compare(sim_pend, real_pend)
    print(f'\n[비교: 재생({cmp_result["sim_total"]}종목) vs 실제 파일({cmp_result["real_total"]}종목)]')
    print(f'  실제 파일 경로: {state_path}')
    print(f'  공통 종목: {cmp_result["common"]}건 (그중 완전일치: {cmp_result["exact_match_common"]}건)')
    print(f'  재생에만 있음: {len(cmp_result["only_in_sim"])}건 {cmp_result["only_in_sim"][:10]}')
    print(f'  실제 파일에만 있음: {len(cmp_result["only_in_real"])}건 {cmp_result["only_in_real"][:10]}')
    if cmp_result['mismatched']:
        print(f'  limit/age 불일치 종목: {len(cmp_result["mismatched"])}건 (상위 10개)')
        for code, diff in list(cmp_result['mismatched'].items())[:10]:
            print(f'    {code}: 재생전용={diff["sim_only"]} 실제전용={diff["real_only"]}')
    else:
        print('  공통 종목 전부 limit/age 완전 일치')

    if args.apply:
        confirm = input(f'\n⚠️  {state_path} 를 재생 결과로 덮어씁니다. 계속하려면 "apply"를 입력: ')
        if confirm.strip() != 'apply':
            print('취소함.')
            return
        new_state = copy.deepcopy(real_state)
        new_state['pending'] = sim_pend
        new_state['updated'] = end_date.isoformat()
        new_state['aged_on'] = end_date.isoformat()
        new_state.pop('day', None)
        tmp = state_path + '.backfill_tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            __import__('json').dump(new_state, f, ensure_ascii=False, indent=1)
        os.replace(tmp, state_path)
        print(f'반영 완료: {state_path} (ordered/기타 필드는 보존, pending만 교체)')


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    main()
