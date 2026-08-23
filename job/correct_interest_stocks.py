# -*- coding: utf-8 -*-
"""interest_stocks 과거 데이터를 일봉(pkl) 기준으로 일괄 정정한다 (2026-08-13 작성).

━━━ 왜 필요한가 ━━━
원본 생성 스크립트(C:\\my-project\\AutoSales.py\\job\\2_finding_stocks_with_increased_volume.py)는
장중에 실행된다(created_at 시간대: 9시 12,290건 / 10시 7,322건 / 11시 4,307건 ...).
그래서 저장된 값이 '그 시각의 장중 스냅샷'이다:
  - today_price_change_pct : 장중 등락률 (종가 확정 전)
  - current_trading_value  : 그 시각까지의 누적 거래대금
  - current_price          : 그 시각의 현재가
종가가 확정된 지금 기준으로 다시 계산해 일관된 데이터로 맞추는 것이 이 스크립트의 목적이다.
(백테스트는 종가를 매수가로 쓰므로, 정정 후에야 DB와 백테스트의 기준이 일치한다.)

━━━ 재계산 정의 (원본 스크립트와 동일하게 맞춤) ━━━
    trading_value            = 거래량 * 종가
    yesterday_close          = 기준일 직전 거래일 종가
    current_price            = 기준일 종가
    today_price_change_pct   = round(pkl 등락률, 2)
    avg5                     = 기준일 제외 직전 5거래일 trading_value 평균
                               (0/비유한이면 직전 20거래일 평균으로 폴백)
    current_trading_value    = 기준일 trading_value
    trading_value_change_pct = round(today_val / avg5 * 100, 2)   (avg5 무효면 100)
⚠️ 원본은 거래대금을 실시간 API(today_amount)에서 받아올 수 있으면 그 값을 썼다. pkl에는
   거래대금 컬럼이 없어 '거래량 × 종가'로 근사한다. 종가 기준으로 통일하는 것이 목적이므로
   이 근사를 채택했지만, 체결단가 가중이 아니라서 실제 거래대금과는 소폭 차이가 난다.

━━━ target 정정 ━━━
재계산 등락률이 TODAY_RATE_OF_INCREASE(3%) 미만이면 breakaway 계열로 내린다.
매핑은 기존 update_stocks_break_away()와 동일하게 유지한다:
    low*        → breakaway_low
    interest    → breakaway
    interest_v2 → breakaway_v2
이미 breakaway 계열인 행은 등락률이 3% 이상이어도 되돌리지 않는다(단방향).
breakaway 지정 사유가 등락률만이 아닐 수 있어서다.

━━━ UNIQUE 충돌 처리 (중요) ━━━
interest_stocks에는 UNIQUE (stock_code, target, created_at::date) 인덱스
(interest_stocks_code_target_daily)가 있다. target을 breakaway로 내릴 때 같은 종목·같은 날에
이미 그 breakaway 행이 있으면 충돌한다(2026-08-13 기준 981건 중 522건).
정체는 '저녁 배치가 같은 종목을 같은 날 두 번 잡은 중복 신호'다. 예:
    009970 2026-06-10  19:43 target=breakaway / 20:18 target=interest
정정하면 두 행 모두 같은 일봉에서 계산되므로 6개 필드 값이 완전히 같아진다. 그래서 한 행을
지워도 잃는 정보가 없다. 기존 update_stocks_break_away()도 같은 상황을 DELETE로 처리한다.
같은 키를 놓고 경합하면 '실제로 target이 바뀌는 행'을 남기고 나머지를 지운다(동률이면 최신 id).

━━━ 사용법 ━━━
    venv/Scripts/python.exe job/correct_interest_stocks.py            # DRY RUN (기본, DB 미변경)
    venv/Scripts/python.exe job/correct_interest_stocks.py --apply    # 실제 반영
    venv/Scripts/python.exe job/correct_interest_stocks.py --apply --no-backup

--apply 시 반영 전에 interest_stocks_bak_<YYYYMMDD_HHMMSS> 백업 테이블을 만든다.
되돌리려면:
    BEGIN;
    DELETE FROM interest_stocks;
    INSERT INTO interest_stocks SELECT * FROM interest_stocks_bak_<...>;
    COMMIT;
"""
import os
import sys
import datetime
from collections import Counter

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding='utf-8')   # 콘솔이 cp949면 한글이 깨진다
except Exception:
    pass

from config.db_connect import db_pool

PICKLE_DIR = r'C:\my-project\AutoSales.py\data\pickle'
TODAY_RATE_OF_INCREASE = 3.0     # 원본 스크립트의 동명 상수와 같은 의미
BATCH_SIZE = 500

BREAKAWAY_MAP = [                # (판정 함수, 바꿀 target). 위에서부터 먼저 맞는 것.
    (lambda t: t.startswith('low'), 'breakaway_low'),
    (lambda t: t == 'interest_v2', 'breakaway_v2'),
    (lambda t: t == 'interest', 'breakaway'),
]

_pkl_cache = {}


def load_pkl(code):
    if code in _pkl_cache:
        return _pkl_cache[code]
    path = os.path.join(PICKLE_DIR, f'{code}.pkl')
    df = None
    if os.path.exists(path):
        try:
            df = pd.read_pickle(path)
            if not isinstance(df.index, pd.DatetimeIndex) or '종가' not in df.columns:
                df = None
        except Exception:
            df = None
    _pkl_cache[code] = df
    return df


def recompute(code, base_date):
    """기준일의 재계산 값을 dict로 반환. 계산 불가면 (None, 사유)."""
    df = load_pkl(code)
    if df is None:
        return None, 'pkl없음'

    idx = df.index.searchsorted(pd.Timestamp(base_date))
    if idx >= len(df) or df.index[idx].date() != base_date:
        return None, '해당일봉없음'
    if idx < 1:
        return None, '직전일없음'

    closes = df['종가'].astype(float)
    tv = df['거래량'].astype(float) * closes

    today_val = float(tv.iloc[idx])
    avg5 = tv.iloc[max(0, idx - 5):idx].mean()
    if not np.isfinite(avg5) or avg5 <= 0:
        avg5 = tv.iloc[max(0, idx - 20):idx].mean()
    if not np.isfinite(avg5) or avg5 <= 0:
        avg5, tvc = 0.0, 100.0
    else:
        tvc = round(today_val / avg5 * 100, 2)

    chg = df['등락률'].iloc[idx] if '등락률' in df.columns else np.nan
    if not np.isfinite(chg):     # 등락률 컬럼이 비면 직전 종가로 직접 계산
        prev = float(closes.iloc[idx - 1])
        chg = (float(closes.iloc[idx]) / prev - 1) * 100 if prev else 0.0

    # 가격·거래대금은 원화 정수다 — 소수점이 붙으면 안 된다(전 종목 nation='kor').
    # pkl은 float으로 들고 있어서 그대로 str()하면 "1000.0"이 저장된다.
    return {
        'yesterday_close': int(round(float(closes.iloc[idx - 1]))),
        'current_price': int(round(float(closes.iloc[idx]))),
        'today_price_change_pct': round(float(chg), 2),      # 등락률은 소수점 유지
        'avg5d_trading_value': int(round(avg5)),
        'current_trading_value': int(round(today_val)),
        'trading_value_change_pct': tvc,                     # 비율은 소수점 유지
    }, None


def breakaway_target_for(origin_target):
    """등락률 미달 시 내려갈 target. 매핑 대상이 아니면 None."""
    t = (origin_target or '').strip()
    if t.startswith('break'):     # 이미 breakaway 계열 → 단방향 원칙상 건드리지 않는다
        return None
    for matches, new_target in BREAKAWAY_MAP:
        if matches(t):
            return new_target
    return None


def as_float(v):
    try:
        return float(str(v).replace(',', ''))
    except (TypeError, ValueError):
        return None


def changed(old_raw, new_val, rel_tol=0.001):
    old = as_float(old_raw)
    if old is None:
        return True
    denom = max(abs(old), abs(float(new_val)), 1e-9)
    return abs(float(new_val) - old) / denom > rel_tol


def main():
    apply_mode = '--apply' in sys.argv
    do_backup = '--no-backup' not in sys.argv

    print('=' * 78)
    print('interest_stocks 정정 ' + ('[APPLY — 실제 반영]' if apply_mode else '[DRY RUN — DB 미변경]'))
    print('=' * 78)

    with db_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT id, created_at::date, stock_code, target,
                                  yesterday_close, current_price, today_price_change_pct,
                                  avg5d_trading_value, current_trading_value,
                                  trading_value_change_pct
                           FROM interest_stocks ORDER BY id""")
            rows = cur.fetchall()
    print(f'대상 {len(rows):,}행\n')

    fail = Counter()
    field_changed = Counter()
    target_changed = Counter()
    planned = []          # {id, values, final_target, key, flipped}
    ok = 0

    for (rid, base_date, code, target, y_c, c_p, t_pct, a5, c_tv, tv_pct) in rows:
        new, err = recompute(code, base_date)
        if new is None:
            fail[err] += 1     # 재계산 불가(상장폐지·거래정지 등) → 원본 그대로 둔다
            continue
        ok += 1

        for key, old_raw in (('yesterday_close', y_c), ('current_price', c_p),
                             ('today_price_change_pct', t_pct), ('avg5d_trading_value', a5),
                             ('current_trading_value', c_tv), ('trading_value_change_pct', tv_pct)):
            if changed(old_raw, new[key]):
                field_changed[key] += 1

        final_target, flipped = target, False
        if new['today_price_change_pct'] < TODAY_RATE_OF_INCREASE:
            bt = breakaway_target_for(target)
            if bt:
                final_target, flipped = bt, True
                target_changed[f'{target} → {bt}'] += 1

        planned.append({
            'id': rid,
            'key': (code, final_target, base_date),
            'flipped': flipped,
            'values': (str(new['yesterday_close']), str(new['current_price']),
                       str(new['today_price_change_pct']), str(new['avg5d_trading_value']),
                       str(new['current_trading_value']), str(new['trading_value_change_pct']),
                       final_target),
        })

    # UNIQUE (stock_code, target, created_at::date) 충돌 해소.
    # 같은 키를 두 행이 다투면 '실제로 target이 바뀌는 행'을 남기고(동률이면 최신 id) 나머지는 지운다.
    by_key = {}
    for p in planned:
        by_key.setdefault(p['key'], []).append(p)
    delete_ids, keep = [], []
    for key, group in by_key.items():
        if len(group) == 1:
            keep.append(group[0])
            continue
        group.sort(key=lambda p: (p['flipped'], p['id']), reverse=True)
        keep.append(group[0])
        delete_ids.extend(p['id'] for p in group[1:])

    updates = [(*p['values'], p['id']) for p in keep]

    print(f'재계산 성공 {ok:,}행 / 실패 {sum(fail.values()):,}행 (실패분은 원본 유지)')
    for k, v in fail.most_common():
        print(f'    {k}: {v:,}')
    print()
    print('값이 바뀌는 행 (0.1% 초과 기준):')
    for key in ('yesterday_close', 'current_price', 'today_price_change_pct',
                'avg5d_trading_value', 'current_trading_value', 'trading_value_change_pct'):
        pct = field_changed[key] / ok * 100 if ok else 0
        print(f'    {key:<26} {field_changed[key]:>7,}  ({pct:5.1f}%)')
    print()
    print(f'target 변경 {sum(target_changed.values()):,}행:')
    for k, v in target_changed.most_common():
        print(f'    {k}: {v:,}')
    print()
    print(f'UNIQUE 충돌로 삭제될 중복 행: {len(delete_ids):,}행')
    print(f'최종 UPDATE 대상: {len(updates):,}행')
    print()

    if not apply_mode:
        print('DRY RUN이라 DB를 변경하지 않았습니다. 실제 반영하려면 --apply 를 붙여 다시 실행하세요.')
        return 0

    with db_pool.connection() as conn:
        try:
            with conn.cursor() as cur:
                if do_backup:
                    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                    bak = f'interest_stocks_bak_{stamp}'
                    cur.execute(f'CREATE TABLE {bak} AS SELECT * FROM interest_stocks')
                    cur.execute(f'SELECT count(*) FROM {bak}')
                    print(f'백업 테이블 생성: {bak} ({cur.fetchone()[0]:,}행)')

                # 중복 행을 먼저 지워야 UNIQUE 인덱스가 비어 UPDATE가 통과한다.
                if delete_ids:
                    for i in range(0, len(delete_ids), BATCH_SIZE):
                        chunk = delete_ids[i:i + BATCH_SIZE]
                        cur.execute('DELETE FROM interest_stocks WHERE id = ANY(%s)', (chunk,))
                    print(f'중복 행 삭제: {len(delete_ids):,}행')

                sql = """
                    UPDATE interest_stocks
                       SET yesterday_close          = %s,
                           current_price            = %s,
                           today_price_change_pct   = %s,
                           avg5d_trading_value      = %s,
                           current_trading_value    = %s,
                           trading_value_change_pct = %s,
                           target                   = %s,
                           updated_at               = now()
                     WHERE id = %s
                """
                for i in range(0, len(updates), BATCH_SIZE):
                    cur.executemany(sql, updates[i:i + BATCH_SIZE])
                    print(f'  ... {min(i + BATCH_SIZE, len(updates)):,}/{len(updates):,}', end='\r')
            conn.commit()
            print(f'\n반영 완료: UPDATE {len(updates):,}행 / DELETE {len(delete_ids):,}행')
        except Exception:
            conn.rollback()
            print('\n오류 발생 — 롤백했습니다.')
            raise
    return 0


if __name__ == '__main__':
    sys.exit(main())
