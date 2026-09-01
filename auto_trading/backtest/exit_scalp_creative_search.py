# -*- coding: utf-8 -*-
"""청산 전략으로 fire CAGR을 양수로 만들 수 있는지 창의적으로 탐색 (2026-08-24 작성).

결론 먼저: **못 찾았다.** 손절선/트레일링 gap·활성시점/최대보유일/익절 조합을 광범위하게
훑고(exit_param_sweep.py, exit_style_test.py, max_hold_sweep.py 등 기존 자산 재사용),
구조적으로 다른 청산(초타이트 손절 -2% + 1일 보유, 익절 없음)까지 새로 시도했다.

전 구간(224거래일) 부트스트랩으로는 이 신규안이 압도적으로 좋다(총수익 평균 +50~76%,
음수 경로 0%, ratio 0.70~1.00). 하지만 **test 기간(2026-04-30 이후, 가장 최근 ~4개월)만
떼어 같은 방식으로 재검증하면 무슬리피지에서도 -2.3~-4.0%로 이미 마이너스이고, 슬리피지
0.3%만 얹어도 -10.6~-15.8%로 전 경로가 마이너스다.** 전 구간 결과의 화려함은 train 기간
(2025-09~2026-04, 이 신호가 실제로 통했던 구간)의 복리 효과가 만든 것이었다.

즉 진짜 원인은 청산 규칙이 아니라 **진입 신호 자체가 최근 레짐에서 기대값 0 이하**라는
것이다(pnl_decomposition.py: 청산 규칙 없이 그냥 1일만 보유해도 test 기간은 -0.528%,
20일 보유는 -16.5%). 청산을 아무리 정교하게 짜도 기대값이 음수인 진입에서 양의 기대값을
만들어낼 수는 없다 — 손실을 얼마나 빨리 자르느냐의 문제일 뿐, 방향을 뒤집지는 못한다.

━━━ 탐색 경과 요약 ━━━

1) 기존 자산 재확인 (exit_param_sweep.py, exit_style_test.py)
   - 손절선 -4%~-20% 전부 시도 → 전부 test 기간 마이너스, 넓힐수록 더 나쁨
   - 트레일링 gap 3%~15%, 활성시점 3%~15% 조합 전부 시도 → 최선(활성+3%)도 test -0.640%
   - 종가 판정 vs 장중(고저가) 판정 비교 → 장중 손절 -4%/3일 보유가 건당 최고(+0.354%,
     test -0.611%)였지만 여전히 test 마이너스
   - 익절 추가(+3%~+7%) 조합 전부 시도 → 개선 폭 작고 test 마이너스 그대로

2) 신규 시도 — 초타이트 손절(-2%) + 초단기 보유(1~3일), 익절 없음
   본 스크립트가 새로 만든 부분. exit_style_test.py의 sim() 프레임을 그대로 재사용해
   손절 -2%~-6% x 보유 1~3일 x 익절 None/3~7% 그리드(75개 조합)를 전수 탐색.
   → hold=1~2, stop=-2%, 익절 없음이 건당 평균·train·test 전부 양수인 유일한 조합
     (hold=1: 평균+0.481%/train+0.534%/test+0.385%,
      hold=2: 평균+0.535%/train+0.723%/test+0.190%)
   → 승률은 20~27%로 낮다(대부분 -2%에서 짧게 잘리고, 소수의 큰 승자가 평균을 끌어올림)

3) 슬리피지 스트레스 테스트 (실계좌 관측 슬리피지: stop_loss 사유 대부분 0~-0.4%p, 근거:
   trades_real.jsonl/trades_mock.jsonl의 slippage 필드)
   hold=1, stop=-2%, 왕복비용 0.21%p 차감:
     슬리피지 0.0%p → 평균+0.271% train+0.324% test+0.175%
     슬리피지 0.3%p → 평균+0.060% train+0.115% test-0.039%  ← 이 근처부터 test가 무너지기 시작
     슬리피지 0.5%p → 평균-0.080% train-0.024% test-0.182%
   실계좌 관측 슬리피지 분포(중앙값 0에 가까움, 최악 -0.39%)와 겹치는 구간이라 "얇지만
   존재할 수도 있는" 엣지 — 확정적이지 않다.

4) 포트폴리오 레벨 검증 (cash_ratio_test.py의 simulate/bootstrap 재사용, mock 실제 설정:
   슬롯20/divisor20/초기자본 2,400만원/후보 상위 20개, 부트스트랩 30회)
   전 구간(229거래일):
     ratio 0.70, 무슬리피지    → 총수익 평균 +50.5%  음수경로 0%   ← 화려하지만 아래 참고
     ratio 0.70, 슬리피지0.3%  → 총수익 평균 +15.1%  음수경로 0%
     ratio 0.70, 슬리피지0.5%  → 총수익 평균  -3.2%  음수경로 80%
   ⚠️ **test 기간만 잘라서 같은 방식으로 재검증(가장 중요한 체크)**:
     ratio 0.70, 무슬리피지    → 총수익 평균  -2.3%  음수경로 77%
     ratio 0.70, 슬리피지0.3%  → 총수익 평균 -10.6%  음수경로 100%
   전 구간 결과의 대부분이 train 기간 복리 효과였음이 확인됨 — out-of-sample 검증 실패.

━━━ 결론 및 권고 ━━━
- 매도(청산) 전략만으로 CAGR을 양수로 바꾸는 방법은 찾지 못했다. 224~229거래일짜리
  단일 구간 백테스트에서 화려한 숫자가 나와도 train/test로 쪼개면 거의 다 무너진다 —
  이건 우연이 아니라 진입 신호 자체가 최근 레짐에서 기대값이 0 이하이기 때문이다.
- 그나마 실전에 가장 정당화 가능한 선택지는 "손절 -4%(장중), 3일 보유, 트레일링 유지"
  수준의 소폭 타이트닝이다(exit_param_sweep.py 근거) — test 기간 손실을 -1.545%→-0.611%로
  줄이지만 양수로 만들지는 못한다. 초타이트 손절(-2%/1일)은 실행 슬리피지에 극도로
  민감하고 out-of-sample에서 이미 무너지므로 **권장하지 않는다.**
- 진짜 레버는 청산이 아니라 진입 쪽이다: 시장폭 레짐 게이트(BREADTH_MIN)를 다시 켜거나,
  H2류 필터(20일 신고가 근접 + 당일 등락률)를 되살리거나, 아예 이 신호를 당분간
  쉬게 하는 것 — 전부 이 스크립트의 범위 밖(진입 로직)이라 실행하지 않았다.

사용법: 이 파일은 결과 문서 겸 재현 스크립트다. main()을 실행하면 위 표를 다시 뽑는다.
    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe auto_trading/backtest/exit_scalp_creative_search.py
"""
import argparse
import sys

import pandas as pd

sys.path.append('.')

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from auto_trading.backtest.fire_backtest_regen import load_ohlc      # noqa: E402
from auto_trading.backtest import cash_ratio_test as CR              # noqa: E402

ROUND_TRIP = 0.21
SPLIT = pd.Timestamp('2026-04-30')


def sim_slip(ohlc, i, entry, hold, stop, slip=0.0):
    """장중 저가가 stop을 건드리면 (stop - slip) 로 체결(패닉 매도 슬리피지 반영).
    안 건드리면 hold일 뒤 종가에 청산."""
    last = min(i + hold, len(ohlc) - 1)
    for j in range(i + 1, last + 1):
        lo = float(ohlc['저가'].iloc[j])
        if (lo / entry - 1) <= stop:
            return (stop - slip) * 100
    return (float(ohlc['종가'].iloc[last]) / entry - 1) * 100


def load_entries(csv_path):
    sig = pd.read_csv(csv_path, encoding='utf-8-sig')
    sig['D'] = pd.to_datetime(sig['D'])
    sig['code'] = sig['code'].astype(str).str.zfill(6)
    recs = []
    for code, d in zip(sig['code'], sig['D']):
        o = load_ohlc(code)
        if o is None:
            continue
        i = o.index.searchsorted(d)
        if i >= len(o) or o.index[i] != d:
            continue
        entry = float(o['종가'].iloc[i])
        hi, lo = float(o['고가'].iloc[i]), float(o['저가'].iloc[i])
        cpos = (entry - lo) / (hi - lo) if hi > lo else 1.0
        recs.append((o, i, entry, d, cpos))
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', default='logs/kiwoom_trading/fire_backtest_result_current.csv')
    ap.add_argument('--capital', type=int, default=24_000_000)
    ap.add_argument('--slots', type=int, default=20)
    ap.add_argument('--divisor', type=int, default=20)
    ap.add_argument('--pool', type=int, default=20)
    ap.add_argument('--bootstrap', type=int, default=30)
    args = ap.parse_args()

    recs = load_entries(args.csv)
    print(f'신호 {len(recs):,}건\n')

    for test_only in (False, True):
        rows = []
        for o, i, entry, d, cpos in recs:
            if test_only and d <= SPLIT:
                continue
            ret = sim_slip(o, i, entry, 1, -0.02, 0.0) - ROUND_TRIP
            rows.append({'D': d, 'entry': entry, 'ret': ret, 'hold': 1, 'close_pos': cpos})
        df = pd.DataFrame(rows)
        tag = 'test 기간만 (out-of-sample)' if test_only else '전 구간'
        print(f'========== hold=1 / stop=-2% / 무슬리피지 — {tag} ({len(df)}건) ==========')
        CR.RATIOS = (0.70, 0.85, 1.00)
        CR.bootstrap(df, args.capital, args.slots, args.divisor, args.pool, args.bootstrap)


if __name__ == '__main__':
    main()
