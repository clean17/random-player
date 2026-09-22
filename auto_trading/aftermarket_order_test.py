# -*- coding: utf-8 -*-
"""KRX 신설 애프터마켓(16:00~20:00, 2026-09-14~)에서 주문이 실제로 처리되는지 확인. (Python 3.8)

왜 필요한가
  지금 kiwoom_api.place_order()가 문서화해둔 trde_tp는 '0'(지정가)/'3'(시장가)뿐이고, 이
  신설 세션 전용 코드가 있는지 없는지 이 저장소 어디에도 확인된 기록이 없다(openapi.kiwoom.com
  공지 게시판이 JS 렌더링이라 자동으로 못 읽었다 — 2026-09-12). NXT 애프터마켓 때는 시장가
  주문이 실제로 거부됐던 전례(407022)가 있어서, 문서 대신 직접 테스트로 확인한다.

⚠️ 반드시 KIWOOM_ENV=mock 으로만 실행할 것 (실계좌 금지 — 지정가는 안 체결되게 설계했지만
   시장가는 실제로 체결/취소돼 모의자산이 움직인다).
⚠️ 반드시 16:00~20:00 사이, 2026-09-14(월) 이후에 실행할 것 — 그 전엔 세션 자체가 없다.

사용법:
    KIWOOM_ENV=mock venv/Scripts/python.exe -m auto_trading.aftermarket_order_test 005930

하는 일:
  1) 지정가 1주를 하한가 바로 위(=사실상 체결 안 됨)로 넣어본다 → 접수/거부만 확인, 곧 취소.
  2) 시장가 1주를 매수해본다(모의 자산이라 실제 체결돼도 손실 아님) → 접수되면 그 자리에서
     같은 수량을 시장가로 되팔아 포지션을 정리한다(exit 로직이 쓰는 것과 동일한 함수).
  3) 결과를 요약 출력한다 — 이 스크립트 결과를 보고 kiwoom_trailing_stop.py 모듈 docstring의
     '검증 전' 문구를 갱신할 것.
"""
import datetime
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from auto_trading import kiwoom_api as api  # noqa: E402


def _ok(res):
    return isinstance(res, dict) and str(res.get('return_code', '')) == '0'


def main():
    if os.getenv('KIWOOM_ENV') != 'mock':
        print('⚠️ KIWOOM_ENV=mock 으로만 실행하세요. 지금 KIWOOM_ENV=%r' % os.getenv('KIWOOM_ENV'))
        return

    now = datetime.datetime.now()
    aftermarket = datetime.time(16, 0) <= now.time() < datetime.time(20, 0)
    if not aftermarket:
        print('⚠️ 지금은 애프터마켓 시간(16:00~20:00)이 아닙니다(현재 %s). 그래도 계속 진행은'
              ' 하지만, 결과가 "거부"로 나와도 그게 애프터마켓 때문인지 단순 장외시간 때문인지'
              ' 구분이 안 됩니다 — 16:00~20:00에 다시 실행하세요.' % now.strftime('%H:%M:%S'))

    code = sys.argv[1] if len(sys.argv) > 1 else '005930'
    acnt_no, acnt_pwd = api.get_account_credentials()
    print('=' * 60)
    print('KRX 애프터마켓 주문 테스트 — %s (mock, 계좌 %s)' % (code, acnt_no))
    print('=' * 60)

    px = api.get_current_price(code)
    print('현재가: %s' % px)
    if px <= 0:
        print('현재가 조회 실패 — 시세 자체가 안 나오면 애프터마켓 조회도 아직 지원 전일 수 있습니다.')
        return

    # ── 1) 지정가: 하한가 바로 위 1틱 (사실상 체결 안 됨) ──────────────────────
    from auto_trading import kiwoom_v8_strategy as v8
    d = v8._load_daily(code)
    prev_close = v8.prev_close_of(d) if d is not None and len(d) >= 2 else None
    print()
    print('[1] 지정가 주문 테스트')
    if prev_close:
        lo = v8.lower_limit_price(prev_close)
        limit = lo + v8._tick(lo)
        print('  전일종가 %d / 하한가 %d / 시도 지정가 %d' % (prev_close, lo, limit))
        res = api.place_order(code, 1, limit, side='1', trde_tp='0', dmst_stex_tp='KRX')
        print('  응답:', res)
        limit_ok = _ok(res)
        print('  결과:', '✅ 접수됨' if limit_ok else '❌ 거부됨')
        if limit_ok and res.get('ord_no'):
            try:
                cres = api.cancel_order(res['ord_no'], code, 1, side='1')
                print('  (정리) 취소 응답:', cres)
            except Exception as e:
                print('  (정리) 취소 실패 — HTS/MTS에서 직접 취소하세요:', e)
    else:
        print('  일봉 데이터 없음 — 지정가 테스트 스킵')
        limit_ok = None

    # ── 2) 시장가: 1주 매수 후 즉시 되팔기 (exit 로직과 동일한 함수) ────────────
    print()
    print('[2] 시장가 주문 테스트 (exit 로직의 sell_market과 동일 경로)')
    buy_res = api.buy_market(code, 1)
    print('  매수 응답:', buy_res)
    market_buy_ok = _ok(buy_res)
    print('  매수 결과:', '✅ 접수됨' if market_buy_ok else '❌ 거부됨')
    if market_buy_ok:
        time.sleep(2)
        sell_res = api.sell_market(code, 1)
        print('  되팔기 응답:', sell_res)
        market_sell_ok = _ok(sell_res)
        print('  되팔기 결과:', '✅ 접수됨' if market_sell_ok else '❌ 거부됨 — 포지션이 남았을 수 있습니다, 직접 확인하세요')
    else:
        market_sell_ok = None

    print()
    print('=' * 60)
    print('요약: 지정가=%s  시장가매수=%s  시장가매도=%s'
          % (limit_ok, market_buy_ok, market_sell_ok))
    print('=' * 60)


if __name__ == '__main__':
    main()
