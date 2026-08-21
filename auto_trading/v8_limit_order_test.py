# -*- coding: utf-8 -*-
"""지정가 주문 동작 확인 — 1주만 접수하고 바로 취소한다. (Python 3.8)

kiwoom_api.place_order 는 trde_tp='0'(지정가)을 지원하지만 이 계좌에서 한 번도
써본 적이 없다. v8 전략을 켜기 전에 반드시 이 스크립트로 확인할 것.

사용법 (장중에 실행):
    venv/Scripts/python.exe -m auto_trading.v8_limit_order_test 005930

체결되지 않도록 현재가의 50% 가격에 1주 매수 주문을 넣는다.
접수되면 주문번호를 출력하고, 미체결 주문 목록에서 확인한 뒤 안내를 출력한다.
⚠️ 취소 API 래퍼가 없으므로 **HTS/MTS에서 직접 취소**해야 한다.
"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from auto_trading import kiwoom_api as api  # noqa: E402


def main():
    code = sys.argv[1] if len(sys.argv) > 1 else '005930'
    acnt_no, acnt_pwd = api.get_account_credentials()
    print('환경 KIWOOM_ENV=%s / 계좌 %s' % (os.getenv('KIWOOM_ENV'), acnt_no))
    px = api.get_current_price(code)
    print('%s 현재가 %d' % (code, px))
    if px <= 0:
        print('현재가 조회 실패 — 장중에 실행하세요.')
        return
    from auto_trading import kiwoom_v8_strategy as v8
    d = v8._load_daily(code)
    if d is None or len(d) < 2:
        print('일봉 없음 — 다른 종목으로 시도하세요.')
        return
    prev_close = v8.prev_close_of(d)
    if not prev_close:
        print('전일 종가 산출 실패')
        return
    lo = v8.lower_limit_price(prev_close)
    limit = lo + v8._tick(lo)      # 하한가 바로 위 1틱 — 밴드 안이면서 사실상 체결 안 됨
    print('전일(마지막 일봉) 종가 %d / 하한가 %d' % (prev_close, lo))
    print('지정가 매수 시도: 1주 @%d (하한가+1틱 — 밴드 안, 체결 가능성 사실상 없음)' % limit)
    res = api.place_order(code, 1, limit, side='1', trde_tp='0', dmst_stex_tp='KRX')
    print('응답:', res)
    rc = str(res.get('return_code', ''))
    if rc in ('0', ''):
        print('\n✅ 지정가 주문 접수 성공. 주문번호 =', res.get('ord_no'))
        try:
            un = api.get_unfilled_orders(acnt_no, acnt_pwd)
            print('미체결 주문 %d건' % len(un))
            for u in un[:5]:
                print('  ', u)
        except Exception as e:
            print('미체결 조회 실패:', e)
        print('\n⚠️ HTS/MTS에서 이 주문을 직접 취소하세요.')
    else:
        print('\n❌ 지정가 주문 거부 — v8 전략을 켜면 안 됩니다.')
        print('   return_msg:', res.get('return_msg'))


if __name__ == '__main__':
    main()
