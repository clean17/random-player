# -*- coding: utf-8 -*-
"""대기 중인 v8 지정가를 현재 DEPTH 기준으로 다시 계산한다. (Python 3.8)

왜 필요한가
  `run_v8_screen()` 은 스크리닝 시점에 `limit = int(sig_close x (1-DEPTH))` 를 **계산해서
  저장**하고, `_features_now()` 는 저장된 값을 그대로 읽는다. 그래서 `DEPTH` 상수를 바꿔도
  이미 대기 중인 지정가는 옛 깊이로 남아 있고, 새 깊이는 다음 15:55 스크리닝부터만 들어온다.
  전환 당일 아침부터 새 깊이로 주문하려면 저장된 `sig_close` 로 재계산해야 한다.

정당성
  백테스트(`strategy-ab-backtest/dailylimit.scan`)도 각 시그널일 종가 x (1-depth) 로 지정가를
  만들고 각자 10 거래일 창을 갖는다. 저장된 sig_close 로 다시 계산하면 아직 유효한 시그널에
  대해 그 명세를 그대로 재현하는 것이다. age(유효기간 경과일)는 건드리지 않는다.

사용
  python -m auto_trading.v9_reprice_pending            # dry-run (변경 없음)
  python -m auto_trading.v9_reprice_pending --apply    # 백업 후 적용

⚠️ run.py 가 이 파일을 쓰는 시간대(15:52 eod / 15:55 스크리닝 / 장중 60초 매수 사이클)를
   피해서 실행할 것. 장 마감 후~다음날 08:00 이 안전하다.
"""
import datetime
import json
import os
import shutil
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auto_trading.kiwoom_v8_strategy import (  # noqa: E402
    DEPTH, STATE_PATH, VALID_DAYS, _round_tick,
)


def main():
    apply = '--apply' in sys.argv
    if not os.path.exists(STATE_PATH):
        print('상태 파일 없음: %s' % STATE_PATH)
        return 1

    with open(STATE_PATH, 'r', encoding='utf-8') as f:
        st = json.load(f)

    pend = st.get('pending') or {}
    print('대상 파일 : %s' % STATE_PATH)
    print('현재 DEPTH: %.2f  (지정가 = 시그널일 종가 x %.2f)' % (DEPTH, 1.0 - DEPTH))
    print('대기 종목 : %d' % len(pend))

    n_ent = n_chg = n_skip = 0
    ratios = []
    samples = []
    for code, v in pend.items():
        for e in (v.get('limits') or []):
            n_ent += 1
            sc = e.get('sig_close')
            old = e.get('limit')
            if not sc or not old:
                n_skip += 1
                continue
            # ⚠️ 반드시 호가단위로 스냅해야 한다. screen_today() 가 쓰는 식과 동일하게 맞춘다
            #    (`limit = _round_tick(close * (1 - DEPTH))`).
            #    2026-09-04 사고: 첫 판에서 int() 로만 계산해 호가단위를 어겼고, 그날 아침
            #    전 주문이 `[2000](571557:주문단가를 잘못입력하셨습니다)` 로 거부됐다.
            new = int(_round_tick(float(sc) * (1.0 - DEPTH)))
            if new == int(old):
                continue
            n_chg += 1
            ratios.append(new / float(old))
            if len(samples) < 5:
                samples.append((code, e.get('sig_date'), float(sc), int(old), new,
                                e.get('age')))
            if apply:
                e['limit'] = new

    print('지정가 엔트리: %d건 (sig_close 없어 건너뜀 %d건)' % (n_ent, n_skip))
    print('변경 대상    : %d건' % n_chg)
    if ratios:
        print('변경 비율    : 평균 x%.4f (최소 x%.4f / 최대 x%.4f)'
              % (sum(ratios) / len(ratios), min(ratios), max(ratios)))
    print('샘플(종목/시그널일/종가/기존→신규/age):')
    for s in samples:
        print('  %s %s  종가 %,.0f  %,d -> %,d  (age %s)'.replace(',', ',') % s
              if False else '  %s %s  종가 %s  %s -> %s  (age %s)'
              % (s[0], s[1], format(int(s[2]), ','), format(s[3], ','),
                 format(s[4], ','), s[5]))

    # age 분포 — 오늘 15:55 스크리닝에서 만료될 건수를 같이 보여준다
    ages = {}
    for code, v in pend.items():
        for e in (v.get('limits') or []):
            a = e.get('age', 0)
            ages[a] = ages.get(a, 0) + 1
    exp = sum(c for a, c in ages.items() if a >= VALID_DAYS)
    print('age >= %d (다음 스크리닝에서 만료 예정): %d건' % (VALID_DAYS, exp))

    if not apply:
        print('\n[dry-run] 변경하지 않았다. 적용하려면 --apply')
        return 0

    bak = '%s.bak_v9_%s' % (STATE_PATH, datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
    shutil.copy2(STATE_PATH, bak)
    # 오늘자 후보 캐시를 버린다 — daily_candidates() 는 st['day'] 를 하루 캐시하므로,
    # 지정가만 고치고 캐시를 두면 장중 내내 옛 ord_px 로 주문이 나간다
    # (run_v8_screen() 도 같은 이유로 state.pop('day', None) 을 한다).
    if st.pop('day', None) is not None:
        print("오늘자 후보 캐시(st['day']) 제거 — 다음 사이클에 재계산된다")
    tmp = '%s.%d.tmp' % (STATE_PATH, os.getpid())
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(st, f, ensure_ascii=False)
    os.replace(tmp, STATE_PATH)
    print('\n적용 완료. 백업: %s' % bak)

    with open(STATE_PATH, 'r', encoding='utf-8') as f:
        chk = json.load(f)
    print('검증: 대기 종목 %d / 지정가 엔트리 %d'
          % (len(chk.get('pending') or {}),
             sum(len(v.get('limits') or []) for v in (chk.get('pending') or {}).values())))
    return 0


if __name__ == '__main__':
    sys.exit(main())
