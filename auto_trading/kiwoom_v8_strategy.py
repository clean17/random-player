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
import threading
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from auto_trading import kiwoom_api as api  # noqa: E402
from auto_trading.kiwoom_api import env_path, get_trading_logger, is_krx_aftermarket_open  # noqa: E402
from auto_trading.kiwoom_trailing_stop import _record_trade  # noqa: E402

# 2026-08-24: 예전엔 getLogger()만 하고 핸들러를 안 붙여서, 스케줄러(run.py) 경로로 돌 때
# INFO 로그가 전부 사라졌다(가동 후 5일간 trading.log에 v8 관련 줄 0건). 상세는
# kiwoom_api.get_trading_logger() docstring 참고.
_log = get_trading_logger('kiwoom_v8')

_last_regap_ts = 0.0   # 마지막으로 현재가를 조회해 live_gap 을 다시 세운 시각
_autobuy_off_logged = False   # '자동 재주문 OFF' 로그를 60초마다 반복하지 않기 위한 래치

# ── 안전 스위치 ──────────────────────────────────────────────────────────────
# 실계좌(KIWOOM_ENV=real)에서 돈다. 2026-08-19 전환 완료.
# 되돌리려면 False + batch_runner 의 kiwoom_fire_buy 주석 해제 + 프로세스 재시작.
V8_ENABLED = True

# ── 파라미터 (ANALYSIS_V8.md §1) ─────────────────────────────────────────────
RUN_MIN = 0.10          # 최근 20일 내 5일 상승률 문턱
RUN_LOOKBACK = 20       # 급등 이력 탐색 구간(거래일)
DEPTH = 0.40            # 지정가 = 종가 x (1-DEPTH)
                        #  ⚠️ 2026-09-13 v11 전환: 0.25 -> 0.40 (사용자 승인).
                        #  **ALLOC 0.04 -> 0.08 과 반드시 한 세트로 움직인다**(아래 ALLOC 주석).
                        #  아래 2026-09-04 그리드는 dailylimit.scan() 의 시간순서 편향 위에서
                        #  나온 값이라 과대평가였다(ANALYSIS_V10.md §2-1, v10_verify_ordering.py
                        #  로 독립 재현: 같은 설정이 +68.9% -> +6.7%). 편향 없는 날짜순 스캐너 +
                        #  ±30% 밴드 + K 제약으로 다시 재면(현행 청산 기준, 단일 변경):
                        #      깊이 25%(현행) +2.10%  MDD -18.5%  Sharpe 0.21  건당 +0.05%
                        #      깊이 40%       +9.04%  MDD  -5.5%  Sharpe 1.10  건당 +1.12%
                        #      + ALLOC 8% 동반 시 +15.38%  MDD -8.6%  3-fold +7/+8/+36
                        #  ⚠️ **값 자체는 스파이크다**: 같은 조건에서 38% +2.26% / 40% +15.38% /
                        #  42% +6.00% 로 이웃의 2.6~6.8배다. "깊게 가는 편이 낫다"는 방향만
                        #  신뢰하고 40%라는 정확한 값은 신뢰하지 않는다(두 독립 엔진이 방향에는
                        #  동의 — ANALYSIS_V10.md 의 현금원장 모델도 d25 음수 / d40 양수).
                        #  ⚠️ 전환 부작용: 체결이 약 1/5로 준다(3.15년 2,622건 -> 551건).
                        #  ⚠️ 기존 대기 지정가는 종가x0.75 기준이라 무효다 — v9_reprice_pending.py
                        #     방식으로 종가x0.60 재계산하거나 유효기간(10거래일) 만료를 기다릴 것.
                        #  근거: strategy-ab-backtest/ANALYSIS_V11.md, ANALYSIS_V11.1.md,
                        #        v11_1_oneat_a_time.py
                        #  되돌리기: DEPTH 0.25 / ALLOC 0.04 를 함께 원복.
                        #
                        #  --- 아래는 2026-09-04 v9 전환 당시 기록(편향 엔진 기준, 참고용) ---
                        #  2026-09-04 v9 전환: 0.30 -> 0.25 (사용자 승인).
                        #  깊이 x 투입비중 전체 그리드 재측정 결과(500만원/슬롯25/최소주문10만원,
                        #  청산은 아래 kiwoom_v8_exit 상수 그대로):
                        #    깊이   투입3%   4%     5%     6%     8%
                        #    -25%  +26.8  +36.7  +39.7  +38.4  +20.7   <- 채택 행
                        #    -30%  +14.3  +19.1  +24.1  +24.0  +26.2   <- 종전
                        #    -35%  +15.9  +21.5  +28.1  +31.3  +35.1
                        #    -40%  +15.9  +21.7  +26.8  +31.9  +29.9
                        #    -45%   +9.8  +13.3  +15.9  +17.0  +17.4
                        #  거래당 기대수익은 깊을수록 단조 상승해 -40%에서 정점(+3.00%)이지만,
                        #  포트폴리오 CAGR 은 -25%가 최고다 — 신호 공급량이 14건/일로 많아
                        #  주문슬롯 K 를 알차게 채우기 때문(-30% 7건/일, -40% 1.6건/일).
                        #  **깊이와 K 는 반드시 같이 움직여야 한다**: -25%를 K=12(투입8%)로
                        #  돌리면 +20.7%로 오히려 떨어진다.
                        #  -40% 행이 MDD -14.5%/Sharpe 1.75로 더 예뻐 보이지만 폐지 종목이
                        #  pickle 에서 삭제돼 측정 불가라 생존편향이 가장 크게 낀 구간이고
                        #  표본도 694건뿐이어서 채택하지 않았다(-25%는 2,444건).
                        #  분석: strategy-ab-backtest/ANALYSIS_V9.md, v9_deep.py
                        #  ⚠️ 되돌리기: DEPTH 0.30 / ALLOC 0.08 / MAX_OPEN_ORDERS 12 를 함께 원복.
VALID_DAYS = 10         # 지정가 유효기간(거래일)
AMOUNT_MIN = 1_000_000_000   # 당일 거래대금 10억
PRICE_MIN = 700

SLOTS = 25              # 동시 보유 상한
ALLOC = 0.08            # 1회 투입 = 평가자산의 8%
                        #  ⚠️ 2026-09-13 v11 전환: 0.04 -> 0.08 (사용자 승인).
                        #  **DEPTH 0.40 과 반드시 한 세트다. 단독으로 올리면 계좌가 망가진다.**
                        #  편향 없는 엔진 + K 제약으로 잰 단일 변경 효과(현행 깊이 25% 유지):
                        #      ALLOC 4% -> 8% 단독:  +2.10% -> **-5.76%**  MDD -18.5% -> -37.4%
                        #  같은 인상을 DEPTH 40% 와 함께 하면:
                        #      깊이40+투입4%  +9.04%  ->  깊이40+투입8%  +15.38%  MDD -5.5%->-8.6%
                        #  이유: 깊이 40%는 노출이 5~7%뿐이라(체결이 드물다) 자금이 놀고 있고,
                        #  투입을 올리는 것이 '레버리지'가 아니라 '빈 공간 채우기'다. 반면 깊이
                        #  25%는 이미 노출 22%라 같은 인상이 순수 레버리지가 된다.
                        #  K 제약 하에서 8%가 정점이다(4% +9.5 / 8% +15.2 / 12% +11.0 / 16% +9.6,
                        #  K가 23->11->7->5 로 무너지기 때문) — 8%를 더 올리지 말 것.
                        #  근거: strategy-ab-backtest/ANALYSIS_V11.md 5절, v11_k_constraint.py
                        #
                        #  --- 아래는 2026-08-19 기록(편향 엔진 기준, 참고용) ---
                        #  2026-08-19 측정(DEPTH=0.30 고정): 투입액을 줄이면 같은 예수금으로
                        #  미체결 주문을 더 걸 수 있고(K ~= 1/ALLOC), CAGR 은 거의 전부 K 로 결정된다.
                        #    10% K=10  CAGR +28.8%  MDD -35.4%  Sh 0.98  F1 +1%
                        #     8% K=12  CAGR +29.2%  MDD -30.5%  Sh 1.07  F1 +7%  <- 구 채택
                        #  6.25% K=16  CAGR +28.5%  MDD -30.8%  Sh 1.16
                        #     4% K=25  CAGR +22.0%  MDD -22.6%  Sh 1.26
                        #   2.5% K=40  CAGR +16.5%  MDD -16.6%  Sh 1.41
                        #
                        #  ⚠️ 2026-09-04 v9 전환: 0.08 -> 0.04 (사용자 승인).
                        #  위 표는 **깊이를 -30%로 고정한 채** 투입비중만 스윕한 것이라
                        #  '깊이와 K 를 같이 움직이는' 조합을 못 봤다. 둘을 같이 스윕하니
                        #  DEPTH=0.25 + 투입 4%(K=25) 가 CAGR +36.7% / MDD -20.3% / Sharpe 1.55 /
                        #  3 fold +27/+39/+50 으로 구 채택(+26.2% / -33.4% / 0.92)을 세 지표
                        #  모두에서 지배한다. 투입 4%와 6%가 +36.7~38.4%로 고원을 이뤄
                        #  단일 셀 과최적화가 아니다. 전체 표는 위 DEPTH 주석 참고.
                        #  분석: strategy-ab-backtest/ANALYSIS_V9.md, v9_deep.py, alloc_k.py
                        #
                        #  실계좌 실측(2026-09-04, 총자산 465만원/보유 15종목/예수금 118만원):
                        #  K = min(MAX_OPEN_ORDERS, 남은슬롯, 예수금÷1회투입금) 에서 **예수금이
                        #  병목**이었다 — 투입 8%면 118만/37.2만 = 3, 4%면 6.4 = 6. 즉 이 전환은
                        #  당장 K 를 3에서 6으로 두 배로 올린다. 보유 15종목(구 8% 사이즈)이
                        #  10거래일 청산 상한으로 빠져나가면서 K 가 남은슬롯 한도까지 더 오른다.
                        #  ⚠️ 백테스트의 K 는 후보 필터로 근사한 값이라 '보유가 늘면 예수금이
                        #  줄어 K 가 같이 준다'는 실계좌 결합을 정확히 반영하지 못한다.
                        #  따라서 실현 CAGR 은 +36.7%보다 낮게 나올 것으로 봐야 한다.
                        #  ⚠️ v8은 모의계좌에서 돌지 않는다(job/batch_runner.py
                        #  create_mock_scheduler 참고) — 이 상수는 실계좌에만 적용된다.
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
# ── 2026-09-14 재검증 (현재 설정 · 편향 없는 엔진) ──────────────────────────
# 위 측정은 DEPTH 30% / 트레일 5% / 보유 10일 / 편향 있는 DL.scan() 기준이었다.
# 현재 설정(DEPTH 40% / 트레일 1.5% / 보유 7일 / ALLOC 8%)에서 날짜순 엔진으로 다시 재도
# 결론이 같고, **격차는 오히려 더 벌어졌다** (strategy-ab-backtest/v13_polling_recheck.py):
#
#   체결일 829건 분류 — 같은 체결가로 두 그룹을 비교(그룹 자체의 질만 본다)
#     지속(종가도 지정가 이하) 395건 47.6%  건당 -1.89%  승률 35.9%  t=-4.27  ← 폴링이 잡는 것
#     반등(종가 > 지정가)      434건 52.4%  건당 +4.58%  승률 69.1%  t=12.73  ← 폴링이 놓치는 것
#     반등폭 중앙값 +3.82% (DEPTH 30% 시절 +2.9%에서 더 커졌다)
#
#   포트폴리오          CAGR      MDD    체결   건당
#     A 현행(K제약)    +17.14%   -8.53%   547  +1.21%
#     B 폴링 상한      +20.30%   -9.68%   672  +1.50%   (지연0 + 예수금 안묶임 = 불가능한 상한)
#     C 폴링 지연      -11.56%  -35.03%   663  -0.02%   (모두 포착하되 체결가=종가)
#     D 폴링 현실       -4.29%  -19.90%   338  +0.10%   (지속만 포착, 체결가=종가)
#   분해: 예수금을 푸는 이득 +3.15%p / 감지 지연 비용 -31.86%p -> 순 -21.43%p
#
# ⭐ 여기서 나오는 **상한선**이 중요하다. 주문을 걸 후보를 아무리 잘 골라도(= B),
#    현행 대비 최대 **+3.15%p** 다. K=11 이 터치의 66%만 덮는 건 사실이지만
#    (v13_coverage.py: K=5 53% / 11 66% / 25 81% / 100 98%), 나머지를 전부 덮어도
#    ALLOC 8% 의 체결시점 현금이 동시보유를 ~12개로 묶어 추가 체결이 포지션으로 다 바뀌지
#    않는다. 즉 '주문이 며칠씩 안 걸린다'는 관찰은 사실이나 비용은 3%p 수준이다.
#    반대로 꼬리(반등)를 놓치는 비용은 20%p 단위다 — **호가창에 미리 걸어두는 것이 본질**.
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
MAX_OPEN_ORDERS = 25    # 동시에 걸어둘 미체결 지정가 주문 수 상한(증거금 보호)
                        #  2026-09-04 v9 전환: 12 -> 25 (사용자 승인). ALLOC 이 8%->4% 로
                        #  반토막 났으므로 25건 x 4% = 예수금 100% 로, 종전 12건 x 8% = 96% 와
                        #  묶이는 비율이 사실상 같다 — 증거금 노출이 늘어나는 변경이 아니다.
                        #  이 상한을 12로 두면 ALLOC 4% 의 이점(K~=1/ALLOC=25)을 절반만 쓰게 된다.
                        #  ⚠️ 실제로는 예수금·남은슬롯이 먼저 묶여 K 가 6~10 수준에서 돈다.
                        #  근거: strategy-ab-backtest/ANALYSIS_V9.md 3~4절
                        #
                        #  2026-09-10 v10: ALLOC 이 4%->10%로 오르면서 25건을 전부 채우면
                        #  예수금 250%가 필요해 산술적으로는 맞지 않지만, 위와 같은 이유로
                        #  실제 동시주문수는 예수금 제약(K~=1/ALLOC=10)에서 먼저 막히므로
                        #  MAX_OPEN_ORDERS 자체를 낮출 필요는 없다(상한일 뿐 실제 도달값이 아님).
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
SNAPSHOT_TOP = 50       # 분석용 일별 후보 스냅샷에 남길 gap 상위 건수 (2026-09-04 추가)
                        #  전량(약 1,000건/일)을 남기면 연 25만건이라 과하다. 상위 50 + 주문이
                        #  나간 종목 전부를 남기면 하루 ~60건(연 1.5만건, 약 3MB)으로,
                        #  슬롯 경쟁에 실제로 참여한 구간은 온전히 보존된다.
                        #  기록: logs/kiwoom_trading/v8_signals_{real,mock}.jsonl
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
# 2026-09-14~: KRX 자체 애프터마켓(16:00~20:00, 기존 시간외단일가 폐지 대체, 15:30~16:00
# 휴장 신설)도 이제 여기서 허용한다(2026-09-12 사용자 요청 — 검증 전 상태로 우선 반영,
# 안 되면 주문 거부 로그로 드러난다는 전제). 상세는 kiwoom_api.is_krx_aftermarket_open
# docstring / kiwoom_trailing_stop.py 모듈 docstring 참고.
KRX_OPEN = datetime.time(9, 0)
KRX_CLOSE = datetime.time(15, 20)


def is_market_open() -> bool:
    now = datetime.datetime.now()
    if now.weekday() >= 5:
        return False
    if KRX_OPEN <= now.time() < KRX_CLOSE:
        return True
    return is_krx_aftermarket_open()


# ── 상태 ─────────────────────────────────────────────────────────────────────
# 2026-08-26 사고: run_v8_buy_cycle(60초)과 run_v8_exit_cycle(30초, mark_sold/
# release_ordered을 통해 이 파일을 건드림)이 같은 프로세스 안에서 동시에 이 파일을
# 읽고 쓰다가 충돌했다 — 둘 다 고정된 이름의 임시파일(STATE_PATH+'.tmp')을 써서,
# 한쪽이 쓰는 도중 다른 쪽이 같은 임시파일을 열거나 os.replace()하면서
# "[WinError 32] 다른 프로세스가 파일을 사용 중" 이 나고 파일 내용이 JSON 두 개가
# 이어붙은 형태로 깨졌다. 이후 모든 읽기가 "Extra data" 파싱 실패로 빈 상태
# ({'pending': {}, 'ordered': {}, ...})를 돌려받았고, 그 빈 'ordered'가 그대로
# 저장되면서 v8이 실제 보유 중인 종목 5개의 소유권 기록이 통째로 사라졌다
# (v8_owned_codes()가 빈 집합을 반환 → kiwoom_v8_exit.py가 그 종목들을 전부
# "내가 산 게 아니다"로 보고 손절/트레일링 관리에서 제외 — 실계좌 보호 공백 발생).
# 고치는 법: (1) 프로세스 전역 락으로 읽기+쓰기를 직렬화, (2) 임시파일 이름에
# pid+스레드ID를 넣어 서로 다른 스레드가 같은 임시파일을 절대 공유하지 않게 함.
_pending_lock = threading.RLock()


def _load_pending() -> Dict:
    with _pending_lock:
        if os.path.exists(STATE_PATH):
            try:
                with open(STATE_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                _log.error('pending 로드 실패: %s', e)
        return {'pending': {}, 'ordered': {}, 'updated': None}


def _save_pending(state: Dict):
    with _pending_lock:
        tmp = f'{STATE_PATH}.{os.getpid()}.{threading.get_ident()}.tmp'
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


def _load_prev_open_codes() -> set:
    """직전 사이클 종료 시점에 실제로 미체결 주문이 걸려 있던 종목코드.

    2026-08-24 사고: 체결 감지를 v8_owned_codes()(한 번이라도 주문 낸 적 있으면 계속 포함)로
    했더니, 이미 v8 주문이 다 체결되어 사라진 지 오래된 종목을 사용자가 대시보드에서
    수동으로 추가매수했을 때도 "v8이 방금 체결시켰다"고 오판해 거래이력에 중복 기록됐다
    (SHD 001770: 수동 2주 기록 직후 v8_buy 2주가 또 기록됨). '한 번이라도 주문한 적 있다'와
    '방금 내 주문이 체결됐다'는 다른 질문이다 — 후자만 판단하려면 "직전 사이클엔 미체결
    주문이 있었는데 이번엔 없어졌다"는 전이(transition)를 봐야 한다."""
    return set(_load_pending().get('open_codes') or [])


def _save_open_codes(codes) -> None:
    st = _load_pending()
    st['open_codes'] = sorted(set(codes))
    _save_pending(st)


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

    지정가(limit)는 시그널일 종가 x (1-DEPTH) 로 **스크리닝 시점에 계산돼 저장된 값**이고
    여기서 바꾸지 않는다. 바뀌는 것은 랭킹 재료(drop5 / ma20 / atr)와 도달 가능성(gap)이다.
    ⚠️ 그래서 `DEPTH` 를 바꿔도 **이미 대기 중인 지정가는 그대로 남는다**(새 깊이는 다음
    15:55 스크리닝부터 반영). 즉시 전체를 새 깊이로 맞추려면 저장된 `sig_close` 로 다시
    계산해야 한다 — `auto_trading/v9_reprice_pending.py` (2026-09-04 v9 전환에 사용).

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


def _load_state_for_env(env: Optional[str] = None) -> Dict:
    """지정한 env의 pending 상태 파일을 조회 전용으로 읽는다 — 대시보드용.

    ⚠️ 매매 루프(run_v8_buy_cycle)는 이 함수를 쓰지 않는다. 그쪽 STATE_PATH는 이
    프로세스(run.py)의 KIWOOM_ENV에 고정돼야 하지만, 대시보드(Flask)는 별도 프로세스라
    env가 요청마다 달라진다 — env_path()로 경로를 매번 다시 계산해야 실전/모의를
    실수로 섞지 않는다.
    """
    path = env_path(os.path.join(os.path.dirname(__file__), 'kiwoom_v8_pending.json'), env)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def get_today_candidates_by_code(env: Optional[str] = None) -> Dict[str, Dict]:
    """오늘자 후보 캐시를 코드로 조회 — 대시보드 주문 목록의 gap/score 조회용.

    ⚠️ daily_candidates()와 달리 **재계산하지 않는다** — 캐시가 없거나 날짜가 다르면
    (장 시작 전 등) 빈 dict를 돌려준다. 조회 요청 하나 때문에 pkl 731개를 다시
    읽어들이는 부작용을 만들지 않기 위함.
    """
    day = _load_state_for_env(env).get('day') or {}
    if day.get('date') != datetime.date.today().isoformat() or not isinstance(day.get('cands'), list):
        return {}
    return {c['code']: c for c in day['cands']}


def get_owned_codes_for_env(env: Optional[str] = None) -> set:
    """v8_owned_codes()의 대시보드용 버전 — 지정한 env를 명시적으로 읽는다."""
    return set((_load_state_for_env(env).get('ordered') or {}).keys())


def get_live_gap_ranking(env: Optional[str] = None, top_n: int = 60) -> List[Dict]:
    """오늘 후보 중 정적 gap 상위 top_n개의 현재가를 조회해 실시간 gap으로 재정렬.

    run_v8_buy_cycle()의 LIVE_REGAP_TOP(=60) 개념과 동일하고 비용도 같다(60개 x 0.143초
    ≈ 8.6초, API 60회) — 다만 이건 v8 매매 루프와 완전히 분리된 **대시보드 조회 전용**
    복사본이라, 여기서 조회한 결과가 v8의 실제 주문/랭킹에는 아무 영향을 주지 않는다.
    LIVE_REGAP=False로 꺼져 있어 실매매 루프 자체는 이 계산을 안 하고 있다.

    ⚠️ 비용이 있으니(순수 계산인 daily_candidates() 캐시 조회와 다름) 호출부가 자동 새로고침
    루프에 넣지 않도록 주의할 것 — 대시보드 쪽에서 수동 새로고침으로만 트리거해야 한다.
    """
    day = _load_state_for_env(env).get('day') or {}
    if day.get('date') != datetime.date.today().isoformat() or not isinstance(day.get('cands'), list):
        return []
    head = sorted(day['cands'], key=lambda x: -x['gap'])[:top_n]
    out = []
    for c in head:
        try:
            px, nm = api.get_current_price_and_name(c['code'], env=env)
        except Exception:
            px, nm = 0, ''
        live_gap = (float(c['ord_px']) / px - 1.0) if px > 0 else c['gap']
        out.append(dict(c, name=nm, cur_px=px, live_gap=live_gap))
    out.sort(key=lambda x: -x['live_gap'])
    return out


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

    # ── 분석용 일별 후보 스냅샷 (2026-09-04 추가) ─────────────────────────────
    # st['day'] 는 **매일 덮어써지므로** 하루 지나면 그날 후보/랭킹/gap 이 사라진다.
    # 사후에 "왜 그 종목을 안 샀나 / 몇 위였나 / gap 이 얼마였나"를 재구성하려면 누적 기록이
    # 필요하다. 전량(약 1,000건)을 매일 남기면 연 25만건이라 gap 상위 SNAPSHOT_TOP 개만
    # 남긴다 — 슬롯 경쟁에 실제로 참여한 구간이 그쪽이고, 멀리 있는 후보는 분석 가치가 낮다.
    ordered_now = v8_owned_codes()
    ranked = sorted(out, key=lambda x: -x['gap'])
    keep = ranked[:SNAPSHOT_TOP]
    keep_codes = {c['code'] for c in keep}
    keep += [c for c in ranked[SNAPSHOT_TOP:] if c['code'] in ordered_now]  # 주문 나간 건 전부
    for rank, c in enumerate(keep, 1):
        api.log_event('v8_signals', {
            'kind': 'candidate', 'date': today, 'rank': rank if c['code'] in keep_codes else None,
            'code': c['code'], 'limit': c.get('limit'), 'ord_px': c.get('ord_px'),
            'prev_close': c.get('prev_close'), 'gap': round(float(c.get('gap') or 0), 5),
            'drop5': c.get('drop5'), 'px_ma20': c.get('px_ma20'), 'atr': c.get('atr'),
            'score': c.get('amount'), 'ordered': c['code'] in ordered_now,
            'cand_total': len(out), 'pend_total': len(pend),
        })
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
    # '한 번이라도 v8이 주문한 적 있다'(_ordered_codes)와 '방금 내 주문이 체결됐다'는 다르다 —
    # 후자만 거래이력에 기록해야 한다. 판단 기준은 "직전 사이클엔 미체결 주문이 있었는데
    # 이번엔 사라졌다"는 전이(transition). 2026-08-24 SHD(001770) 사고: 이 구분이 없어서
    # 이미 오래전에 체결 완료된 종목을 사용자가 대시보드에서 수동으로 추가매수했을 때도
    # "v8이 방금 체결시켰다"고 오판해 거래이력에 중복 기록됐다.
    prev_open_codes = _load_prev_open_codes()

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
                if delta > 0 and code in prev_open_codes:
                    asset_ratio = (px * delta / equity) if equity > 0 else None
                    _record_trade(code, h.get('stk_nm'), 'buy', 'v8_buy', delta, px, px, 0.0,
                                  asset_ratio=asset_ratio)
                    _log.info('v8 매수체결 기록 %s qty=%d(누적%d) px=%.0f', code, delta, qty, px)
                elif delta > 0:
                    _log.info('v8 보유수량 증가 감지했지만 직전 미체결 주문 없음(수동매수 등으로 '
                              '추정) %s qty=%d(누적%d) px=%.0f — 거래이력 기록 생략',
                              code, delta, qty, px)

    # ── 자동 재주문 스위치 (2026-09-14) ─────────────────────────────────────
    # 대시보드에서 '자동 재주문'을 끄면 여기서 멈춘다. 위치가 중요하다 —
    #  · 위(체결 감지)는 그대로 돈다. 스위치를 끄기 전에 이미 걸려 있던 주문이 체결되면
    #    소유권/거래이력/지정가 소진이 정상적으로 기록돼야 한다.
    #  · 아래(후보이탈 취소 / 수량조정 / 신규주문 / 교체)는 전부 '주문을 내는' 동작이라 막는다.
    #    특히 수량조정은 취소 후 곧바로 다시 거는 경로여서, 여기서 안 막으면 사용자가
    #    전량 취소해 둔 주문이 되살아난다.
    # _save_open_codes 는 빼먹지 않는다. 갱신하지 않으면 다음 사이클이 "직전엔 주문이
    # 있었는데 지금 없다"를 계속 참으로 보고 체결 오탐을 낼 수 있다.
    global _autobuy_off_logged
    if not api.is_autobuy_enabled():
        _save_open_codes(open_buy.keys())
        if not _autobuy_off_logged:
            _autobuy_off_logged = True
            _log.info('v8 매수 스킵 — 자동 재주문 OFF (대시보드 스위치). 미체결 %d건은 그대로 둔다',
                      len(open_buy))
            api.log_event('v8_signals', {'kind': 'autobuy_disabled', 'open_orders': len(open_buy)})
        return
    _autobuy_off_logged = False

    # 하루 1회 계산된 캐시를 쓴다 (첫 사이클에서만 pkl 을 읽는다)
    #  · 보유 중 종목 제외      = 동일 종목 중복 보유 금지
    #  · 당일 매도 종목 제외    = sequential_filter 의 두 번째 규칙
    #  · 투자주의환기종목/거래정지/관리종목 제외(무조건) = 2026-09-03, 270520 사례로 요청.
    #    관리종목은 2026-09-07 008290(원풍물산) 사례로 한 번 무조건 차단했다가, 2026-09-08
    #    "관리종목이라도 다 위험한 건 아니다"라는 피드백으로 1000원 미만(동전주)일 때만
    #    제외하도록 완화했었으나, 2026-09-14 "관리종목은 매수 안 되도록" 요청으로
    #    가격 조건 없이 다시 무조건 차단으로 되돌렸다.
    #    ka10099 auditInfo 기준(5분 캐시). 조회 실패 시엔 빈 dict가 와서 아무것도 안
    #    걸러지므로(안전 쪽으로 폴백), 이 필터가 매수를 막지는 않되 보호도 안 해줄 수 있다.
    _sold = sold_today_codes()
    _audit_map = api.get_stock_audit_info_map()
    _AUDIT_BLOCK_HARD = {'투자주의환기종목', '거래정지', '관리종목'}

    def _audit_blocked(c):
        return _audit_map.get(c['code']) in _AUDIT_BLOCK_HARD

    cands = [c for c in daily_candidates()
             if c['code'] not in held and c['code'] not in _sold
             and not _audit_blocked(c)]

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
            api.log_event('v8_signals', {'kind': 'order_cancelled', 'code': code,
                                         'why': 'candidate_dropped'})
        except Exception as e:
            _log.warning('주문취소 실패 %s: %s', code, e)

    room = SLOTS - len(held)
    if room <= 0:
        _save_open_codes(open_buy.keys())   # 다음 사이클의 체결 전이 판단 기준선 갱신
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
            api.log_event('v8_signals', {'kind': 'order_resized', 'code': c['code'],
                                         'qty_from': cur_qty, 'qty_to': tgt_qty,
                                         'ord_px': c['ord_px']})
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
    newly_placed = set()   # 이번 사이클에 새로 낸 주문 — open_buy 딕셔너리엔 안 넣으므로 따로 추적

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
            api.log_event('v8_signals', {
                'kind': 'order_replaced', 'code': worst['code'], 'why': 'regap',
                'live_gap': round(float(worst.get('live_gap') or 0), 5),
                'replaced_by': c['code'],
                'replaced_by_live_gap': round(float(c.get('live_gap') or 0), 5)})
            open_buy.pop(worst['code'], None)
            release_ordered(worst['code'])
            placed -= 1

        res = buy_limit(c['code'], qty, c['ord_px'])
        ok = isinstance(res, dict) and str(res.get('return_code', '')) == '0'
        _log.info('v8 지정가주문 %s %s qty=%d @%d (아침 %.1f%% / 현재 %.1f%%) -> %s',
                  c['code'], '접수' if ok else '거부', qty, c['ord_px'],
                  c['gap'] * 100, c['live_gap'] * 100,
                  res.get('return_msg') if isinstance(res, dict) else res)
        api.log_event('v8_signals', {
            'kind': 'order_placed' if ok else 'order_rejected',
            'code': c['code'], 'qty': qty, 'ord_px': c['ord_px'],
            'gap': round(float(c.get('gap') or 0), 5),
            'live_gap': round(float(c.get('live_gap') or 0), 5),
            'cur_px': c.get('cur_px'), 'limit': c.get('limit'),
            'ord_no': res.get('ord_no') if isinstance(res, dict) else None,
            'msg': res.get('return_msg') if isinstance(res, dict) else str(res),
        })
        if ok:
            placed += 1
            newly_placed.add(c['code'])
            _mark_ordered(c['code'])

    # 다음 사이클의 체결 전이 판단 기준선 갱신 — 이번 사이클에 새로 낸 주문도 포함해야
    # 그 주문이 다음 사이클까지 체결됐을 때 정상적으로 감지된다.
    _save_open_codes(set(open_buy.keys()) | newly_placed)


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
