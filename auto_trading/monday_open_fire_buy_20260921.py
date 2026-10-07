"""1회성 스크립트 — 2026-09-21(월) 장 시작 직후 모의계좌 fire 매수예약 종목 즉시 매수.

배경: 2026-09-18(금) 15:21 정기 fire 매수 실행 이후 대시보드에서 자동매수 대상(reserved)에
종목을 추가로 체크했는데, 그 시점(15:30)엔 이미 동시호가(15:20~15:30)가 끝나 있어 키움
모의투자 서버가 전량 RC4058(모의투자 장종료)로 거부했다. 다음 정규 매수 타이밍(15:21, 동시호가
종가)까지 기다리는 대신, 이번 한 번만 월요일 장 시작 직후(09:00) 바로 사 달라는 요청.

⚠️ 1회성이다 — job/batch_runner.py의 정기 스케줄(15:21 mock_fire_buy)은 건드리지 않는다.
   fire 전략은 원래 '신호일 종가'를 매수가로 가정하고 검증됐고(kiwoom_fire_strategy_mock.py
   헤더 참고), 15:18 연속거래 시장가 대신 15:20~15:30 동시호가로 바꾼 이유도 그 가정과 실제
   체결가 괴리(-0.9%) 때문이었다 — 09:00 장시작가 매수는 그 검증된 가정과 또 다르게 어긋날 수
   있는 예외 실행이다. 되풀이해서 쓸 게 아니라 이번 건 한정.

실행: Windows 작업 스케줄러(schtasks)로 2026-09-21 09:00:05 1회 등록해서 돌린다.
   venv/Scripts/python.exe -X utf8 auto_trading/monday_open_fire_buy_20260921.py

같은 매수 로직(run_fire_buy_cycle)을 재사용하므로, reserved 종목·쿨다운·수동매수 보호 등
기존 필터는 그대로 적용된다 — 09:00에 이미 매수되면 같은 날 15:21 정기잡은 쿨다운으로
자동 스킵되어 중복매수되지 않는다(COOLDOWN_DAYS 로직).

⚠️ 2026-09-21 09:00:07 1차 실행 결과 후보 0종목 — get_interest_stocks_info()의 SQL이
   endDate=오늘·09:00 이후엔 '오늘 신호가 실제로 발생한 종목만' 통과시켜서(당일 상승률
   조건 자체가 당일 가격움직임이 쌓여야 계산되므로 장 시작 직후엔 구조적으로 0건), 장 열자마자는
   신규 신호가 있을 수 없었다. 사용자 의도는 "그날(직전 거래일, 09-18) 당시 fire 조건을 이미
   통과했던 예약종목을 월요일 장 시작가로 사라"는 것이었으므로, get_fire_candidates()에
   end_date를 추가해(=09-18) 그 시점 기준 후보를 그대로 재사용하도록 2차 실행에서 수정했다.

실행 후 이 파일은 지워도 된다(1회성).
"""
import os
# 다른 어떤 import 보다 먼저 — auto_trading 모듈이 import 시점에 이 값을 읽는다 (run_mock.py와 동일 패턴)
os.environ['KIWOOM_ENV'] = 'mock'

import sys
import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from auto_trading.kiwoom_api import KIWOOM_ENV, get_account_credentials, _cfg_for
from auto_trading.kiwoom_fire_strategy_mock import run_fire_buy_cycle, get_fire_candidates

print(f'{datetime.datetime.now()} - monday_open_fire_buy_20260921 시작')

acnt_no, _ = get_account_credentials()
print(f'KIWOOM_ENV={KIWOOM_ENV}, base_url={_cfg_for()["base_url"]}, acnt_no={acnt_no}')

# 직전 거래일(금, 09-18) 기준으로 fire 후보를 다시 얻는다 — endDate가 '오늘(09-21)'이 아니므로
# get_interest_stocks_info()의 '오늘 신호 필요' 게이트가 걸리지 않고, 09-18 15:54에 봤던
# 그 후보 그대로(신규 신호 유무와 무관) 다시 나온다.
LAST_TRADING_DAY = datetime.date(2026, 9, 18)

cands = get_fire_candidates(end_date=LAST_TRADING_DAY)
print(f'{LAST_TRADING_DAY} 기준 fire 조건 통과 후보 {len(cands)}종목')

run_fire_buy_cycle(candidates_end_date=LAST_TRADING_DAY)

print(f'{datetime.datetime.now()} - monday_open_fire_buy_20260921 완료 (결과는 logs/kiwoom_trading/trading_mock.log 참고)')
