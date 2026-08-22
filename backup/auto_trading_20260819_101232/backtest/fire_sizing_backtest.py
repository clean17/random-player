# -*- coding: utf-8 -*-
"""fire 전략 '사이징 규칙' 포트폴리오 재시뮬레이터 (2026-08-11 작성).

auto_trading/kiwoom_fire_strategy.py의 BUY_SLOTS 고정 분모 방식이 매수 예산을 낭비하는 문제를 계기로,
예산 재분배안을 같은 데이터로 검증하기 위해 만들었다.

사용법:
    python auto_trading/backtest/fire_sizing_backtest.py <csv> [모드 ...]
    모드: compare(기본) sweep cap periods monthly mechanism today ratio  /  all

    예) python auto_trading/backtest/fire_sizing_backtest.py logs/kiwoom_trading/fire_backtest_result.csv all

입력 CSV(logs/kiwoom_trading/fire_backtest_result.csv)는 .gitignore의 logs/ 규칙에 걸리지만
재현성을 위해 git add -f로 강제 추적한다. 갱신할 때도 -f가 필요하다.

━━━ 계기가 된 사건 (2026-08-11 15:18 실매매) ━━━
가용현금 3,750,735원 → 한도 2,625,514원(70%) ÷ 20슬롯 = 1픽 131,276원.
후보 18종목 중 7종목이 현재가 > 1픽 예산이라 1주도 못 사서 skip(nocash 39%).
11종목·1,247,020원(한도의 47.5%)만 집행하고 2,503,715원이 남았다.
원인은 kiwoom_fire_strategy.py:314의 slot_budget이 루프 밖에서 한 번만 계산돼
skip된 슬롯 예산이 재분배되지 않는 것.

━━━ 입력 CSV의 기준 (생성 스크립트가 저장소에 없어 데이터에서 역추적, 2026-08-11) ━━━
진입(fire 픽 선정) — 컬럼 최소/최대값에서:
  total_rate >= 8.50 (상한 없음 — 67%가 12% 초과, 최대 90.0)
  count 2~5회, avg_chg >= 5.00, per_day >= 3.80
  (시총 700억/거래대금 40억 조건은 CSV에 컬럼이 없어 확인 불가)
청산 — exit 유형별 ret_pct 분포에서:
  stop     1,773건  median -6.000  min -6.000  → 손절 -6%
  target     513건  max    15.000  median 11.662 → 목표가 +15%
  trailing   370건  median  8.713  min  -2.122  → 트레일링 gap 약 2%
  time         2건  최대 보유 15일

⚠️ 현재 코드와 어긋나는 부분 (절대 수익률을 그대로 믿으면 안 되는 이유):
  손절     -6%      = auto_trading/kiwoom_trailing_stop.py STOP_LOSS_RATE=-0.06  ✓ 일치
  목표가   +15%     ↔ 현재 TARGET_RATES=[] (비활성화)                   ✗ 불일치
  트레일링 gap 2%   ↔ 현재 TRAIL_ACTIVATE_RATE=0.07/TRAIL_GAP=0.05/
                      MIN_PROFIT_FLOOR=0.03                            ✗ 불일치
  최대보유 15일     ↔ 현재 무제한(트레일링 일임)                        ✗ 불일치
  진입조건          ↔ 2026-08-05 H2 필터 제거로 통과 종목이 급증
                      (2026-08-11 실제 fire 통과 89종목 vs CSV 평균 13.2종목) ✗ 불일치
  → 사이징 규칙 간 '상대 비교'는 유효하다(모든 규칙이 같은 ret_pct를 쓴다).
    그러나 절대 수익률(32.0% 등)은 현재 전략의 기대 성과가 아니다. 특히 목표가 +15%는
    수익 상단을 자르던 장치였고(전체 청산의 19.3%, 평균 +11.8%) 지금은 없다.
  (참고: auto_trading/kiwoom_fire_strategy.py docstring의 '손절 -3%' 표기는 실제 코드(-6%)와 다르다.)

━━━ 검증한 규칙 ━━━
  current : 현행. budget = deploy_limit / BUY_SLOTS (고정)
  A1      : 순차 재분배. budget = (deploy_limit - deployed) / 남은 후보 수
  A2      : 균등 재분배. 분모를 '그 예산으로 1주라도 살 수 있는 후보 수'로 수렴시켜 균등 배분
  cap_divisor : 종목당 상한 = deploy_limit / divisor (None이면 무제한)

━━━ 결과 요약 (초기자본 760만원, 201거래일) ━━━
  규칙            총수익%  Sharpe   MDD%  최대단일종목   자본활용도%
  현행 슬롯20        19.5    1.60  -13.8      345,600         48.5
  A-1 상한없음       26.7    1.14  -26.9    6,338,720         -
  A-1 상한20         21.7    1.90  -12.2      345,870         45.5
  A-1 상한12         32.0    2.05  -12.2      624,000         58.9
  A-1 상한10         33.5    1.98  -12.9      764,330         62.8
  A-1 상한8          33.2    1.83  -14.3      956,480         66.9
  A-2 상한12         25.4    1.65  -15.1      604,800         -

1) 상한 없는 재분배는 절대 금지. 후보가 1개인 날(201일 중 7일)에 매수한도 전액이 한 종목에
   들어가 단일종목 6,338,720원 = 초기자본의 83%. MDD가 -13.8% → -26.9%로 정확히 2배.

2) A-2(균등)는 기각. 정렬 편향(금액가중 total_rate - 단순평균)은 A-1의 +0.91보다 작은 +0.37이지만,
   2026-04~07 구간에서 -6.9%로 현행(-6.8%)보다 나빴고 전 구간 수익도 A-1에 일관되게 뒤졌다.
   '이론적으로 편향이 적다'가 실측 성과로 이어지지 않았다.

3) 상한20(= 현행 1픽 예산과 동일)의 개선은 '예산 재분배'가 아니다.
   오늘 케이스(후보 18개)에서 상한20은 현행과 체결이 100% 동일한데도 백테스트는 +2.2%p 개선된다.
   후보 수 구간별로 쪼개보면 원인이 드러난다(현행 → 상한20, 총투입/실현손익):
     후보 1-10개 : 117.0M/+612,207 → 118.3M/+581,755
     후보 11-20개: 146.1M/+1,075,636 → 153.7M/+1,125,853
     후보 21-30개:  94.2M/+147,331 →  87.5M/+140,044
     후보 31개+  :  52.7M/-355,933 →  31.3M/-200,159   ← 현행의 유일한 손실 구간
   후보가 많은 날 (남은한도/남은후보)가 (한도/20)보다 작아지면서 투입을 40% 줄인 효과.
   즉 상한20은 '후보 많은 날 과집중 완화'이고, 오늘의 예산 낭비는 전혀 해결하지 못한다.

4) 상한12의 우위는 계좌 규모 효과가 아니다. 300만~3억까지 훑어도 +11~+19%p로 유지되고,
   nocash%는 19.0%(300만) → 0.0%(3억)로 사라지는데 우위는 그대로다.

5) 상한12의 우위는 '노출 확대'만도 아니다 (처음엔 그렇게 판단했으나 검증에서 틀렸다).
   자본활용도(주식 보유 비율)를 ~60%로 맞춰 비교하면 (mode_ratio / 후보수 구간별 분해):
     현행 r=1.00        : 보유 62.1%, 총수익 19.1%, Sharpe 1.26, MDD -16.9%
     A-1 상한12 r=0.70  : 보유 58.9%, 총수익 32.0%, Sharpe 2.05, MDD -12.2%
     A-1 상한20 r=1.00  : 보유 58.9%, 총수익 27.8%, Sharpe 1.84, MDD -14.3%
   노출이 같은데 수익이 13%p 차이난다. 원인은 자금이 '어디로' 가느냐다 —
   후보 수 구간별 총투입(현행 r=1.00 → 상한12 r=0.70)과 그 구간의 수익률:
     후보 1-10  (+0.45%/건): 165.1M → 196.7M  (+19%)
     후보 11-20 (+0.64%/건): 194.1M → 225.8M  (+16%)
     후보 21-30 (+0.08%/건): 122.3M →  91.4M  (-25%)
     후보 31+   (-0.94%/건):  66.3M →  31.6M  (-52%)
   (남은한도 / 남은후보) 공식은 후보 수에 반비례하는 자동 사이징이다. 후보가 적은 날(급등주가
   드문 날 = 신호가 희소한 날)엔 크게, 후보가 많은 날(시장 과열)엔 작게 산다. 그게 우연히
   수익 구조와 정렬돼 있다. 현행에서 CASH_DEPLOY_RATIO만 올리면 모든 구간에 균등하게 더
   넣으므로 손실 구간 투입도 52.7M → 66.3M로 함께 늘어 Sharpe가 1.60 → 1.26으로 무너진다.
   ⚠️ 단 노출이 큰 설정의 MDD·Sharpe는 여전히 유리하게 왜곡돼 있다 — 보유 포지션을 취득원가로
      평가해서(아래 전제 3) 변동성이 실제보다 작게 잡힌다. r=0.85/1.0의 MDD는 과소평가다.

6) CASH_DEPLOY_RATIO(70%)는 '자산의 70% 보유'가 아니라 '그날 남은 현금의 70%까지 신규 매수'다.
   평균 보유 2.28일이면 정상상태 보유비율 u = h·r/(1+h·r) → r=0.70의 이론 상한은 61.5%다.
   즉 r=0.70으로 70% 보유는 구조적으로 불가능하고, 70% 보유를 원하면 r을 1.0 근처까지 올려야
   하는데 그건 '30% 현금 버퍼' 설계와 정면 충돌한다.
   게다가 현행 규칙은 그 이론값에도 못 미친다 — 한도 소진율이 r과 무관하게 46~48%에 고정된다
   (r을 0.5→1.0으로 두 배 올려도 45.6→48.1%). 병목이 한도가 아니라 (한도/BUY_SLOTS) 분모라서다.
   상한12는 소진율 60%대로 올려 이론값(61.5%)에 거의 도달한다(실측 58.9%).

7) 상한8 이하는 배제. 하락 구간(2026-04~07, 3000만원)에서 -8.1%로 현행 -7.0%보다 나쁘다.
   같은 구간 금액가중 total_rate가 16.79까지 올라가는데(현행 15.48), 상한을 풀면 순차 재분배의
   정렬 편향이 커지고 그게 하락장에서 독이 된다 — 본 전략 docstring의 '높은순 -35%'와 방향이 같다.

8) 왕복비용 0.2%(수수료+거래세)를 넣으면 현행 19.5→8.3%, A-1 상한8 33.2→17.3%.
   체결 2,100건의 고회전이라 비용 가정에 매우 민감하다.

━━━ 전제 (실제 운영과 다른 부분 — 결과 해석 시 반드시 감안) ━━━
  1. reserved(자동매수 대상 체크) 교집합을 재현할 수 없어 'fire 픽 전체가 reserved'로 가정.
     실제로는 후보가 훨씬 적어 슬롯을 덜 쓴다 → 규칙 간 차이는 여기 수치보다 작을 것.
     ★ 이 때문에 본 전략 docstring의 재시뮬레이션 수치가 재현되지 않는다(현행 슬롯20이
       여기선 +19.5%, docstring은 +3.0%). 두 표를 나란히 놓고 비교하면 안 된다.
  2. 거래일 캘린더는 CSV에 등장하는 날짜(201일)만 사용. 신호 없는 날이 빠져 있어 보유일수/쿨다운이
     실제보다 약간 짧게 계산된다. 모든 규칙에 동일하게 적용되므로 상대비교엔 무해.
  3. 보유 포지션은 취득원가로 평가(일별 시가 데이터가 없음). equity 곡선은 청산 시점에만 움직이는
     '실현' 곡선이고 Sharpe/MDD도 그 기준 — 실제 변동성은 이보다 크다. (위 4번 경고 참고)
  4. ret_pct는 수수료/거래세 이전 값. cost 모드로 왕복비용 반영 케이스를 따로 낸다.

━━━ 실제 로직 재현 시 주의한 점 ━━━
  run_fire_buy_cycle()은 get_fire_candidates()를 limit 없이 호출한다(kiwoom_fire_strategy.py:273,
  "limit은 출력용 제한일 뿐 매수 경로에서는 자르지 않는다"). 즉 후보 리스트는 20개로 잘리지 않고
  BUY_SLOTS는 '성공한 매수 20건'에서만 break한다. 1주도 못 산 skip은 슬롯을 소비하지 않고
  다음 후보로 넘어가므로, 후보 64개인 날은 리스트를 깊게 파고든다.
"""
import sys

import numpy as np
import pandas as pd

# auto_trading/kiwoom_fire_strategy.py와 동일하게 유지해야 하는 값
CASH_DEPLOY_RATIO = 0.70
COOLDOWN_DAYS = 2
BUY_SLOTS = 20

DEFAULT_CAPITAL = 7_600_000   # 2026-08-11 기준 실계좌 총자산(로그의 asset_ratio로 역산)


def load(csv_path):
    df = pd.read_csv(csv_path, encoding='utf-8-sig')
    df['D'] = pd.to_datetime(df['D']).dt.date
    # 총상승률 낮은순이 실제 매수 순서 (전략 docstring '쿨다운/슬롯 재검증' 근거)
    return df.sort_values(['D', 'total_rate']).reset_index(drop=True)


def a2_denominator(prices, deploy_limit, slots):
    """A-2 균등 재분배의 분모: '그 예산으로 1주라도 살 수 있는 후보 수'를 수렴시킨다.

    n을 줄이면 예산이 커지고, 예산이 커지면 살 수 있는 후보(n)가 늘어 진동할 수 있다.
    같은 n이 재등장하면 사이클이므로 더 분산되는 쪽(큰 n)을 택해 멈춘다.
    최대 slots건만 체결되므로 분모는 slots를 넘기지 않는다(넘기면 한도를 덜 쓴다).
    """
    if not prices or deploy_limit <= 0:
        return 1
    n = min(len(prices), slots)
    seen = set()
    while True:
        budget = deploy_limit / n
        eligible = min(sum(1 for p in prices if p <= budget), slots)
        if eligible <= 0 or eligible == n:
            break
        if eligible in seen:
            n = max(n, eligible)
            break
        seen.add(n)
        n = eligible
    return max(1, n)


def simulate(df, initial_cash, rule, slots=BUY_SLOTS, cap_divisor=None, round_trip_cost=0.0,
             deploy_ratio=CASH_DEPLOY_RATIO):
    """하루 단위 현금흐름 포트폴리오 시뮬레이션.

    deploy_ratio는 CASH_DEPLOY_RATIO와 같은 의미 — '그날 남은 현금 중 신규 매수에 쓸 최대 비율'.
    보유 목표 비율이 아니다(둘의 관계는 mode_ratio 참고).
    """
    dates = sorted(df['D'].unique())
    by_date = {d: g for d, g in df.groupby('D')}

    cash = float(initial_cash)
    cost_basis = 0.0            # 보유 포지션 취득원가 합
    open_pos = []               # {'exit_idx', 'proceeds', 'cost'}
    last_buy_idx = {}           # code -> 매수일 캘린더 인덱스 (쿨다운용)
    trades = []
    n_attempt = 0               # 예산 판정까지 간 건수(쿨다운 통과)
    n_nocash = 0                # 1주도 못 사서 버려진 건수
    equity_curve = []
    slot_fill = []              # 날짜별 체결 종목 수
    util = []                   # 날짜별 자본 활용도(주식 원가 / 총자산)
    limit_use = []              # 날짜별 한도 소진율(그날 집행액 / 그날 매수한도)

    for i, d in enumerate(dates):
        # 1) 청산 정산 — 당일 매수 전에 현금 회수
        still = []
        for pos in open_pos:
            if pos['exit_idx'] <= i:
                cash += pos['proceeds']
                cost_basis -= pos['cost']
            else:
                still.append(pos)
        open_pos = still

        # 2) 후보: 총상승률 낮은순 전체(자르지 않음 — 위 '재현 시 주의' 참고). 쿨다운만 먼저 제외.
        rows = list(by_date[d].itertuples(index=False)) if d in by_date else []
        live = [r for r in rows
                if not (last_buy_idx.get(r.code) is not None
                        and (i - last_buy_idx[r.code]) < COOLDOWN_DAYS)]

        deploy_limit = max(0.0, cash) * deploy_ratio
        pos_cap = (deploy_limit / cap_divisor) if cap_divisor else float('inf')

        # A-2는 루프 전에 분모를 한 번 확정 → 전 종목 동일 예산(정렬 편향 최소)
        n_den = a2_denominator([r.buy for r in live], deploy_limit, slots) if rule == 'A2' else 1

        deployed = 0.0
        buys_today = 0
        for k, r in enumerate(live):
            if buys_today >= slots:
                break
            n_attempt += 1

            if rule == 'current':
                budget = deploy_limit / slots if slots > 0 else 0.0
            elif rule == 'A1':
                budget = (deploy_limit - deployed) / max(1, len(live) - k)
            elif rule == 'A2':
                budget = deploy_limit / n_den
            else:
                raise ValueError(rule)

            budget = min(budget, pos_cap, deploy_limit - deployed, cash)
            qty = int(budget // r.buy)
            if qty <= 0:
                n_nocash += 1
                continue

            spent = qty * r.buy
            proceeds = spent * (1 + r.ret_pct / 100.0) * (1 - round_trip_cost)
            cash -= spent
            cost_basis += spent
            deployed += spent
            buys_today += 1
            open_pos.append({'exit_idx': min(i + int(r.days), len(dates) - 1),
                             'proceeds': proceeds, 'cost': spent})
            last_buy_idx[r.code] = i
            trades.append({'date': d, 'code': r.code, 'name': r.name, 'qty': qty,
                           'price': r.buy, 'spent': spent, 'ret_pct': r.ret_pct,
                           'total_rate': r.total_rate, 'order': k, 'pnl': proceeds - spent})

        slot_fill.append(buys_today)
        equity_curve.append(cash + cost_basis)
        util.append(cost_basis / (cash + cost_basis) if (cash + cost_basis) > 0 else 0.0)
        if live and deploy_limit > 0:
            limit_use.append(deployed / deploy_limit)

    for pos in open_pos:          # 잔여 포지션 청산
        cash += pos['proceeds']
        cost_basis -= pos['cost']
    final = cash + cost_basis
    equity_curve.append(final)

    eq = np.array(equity_curve, dtype=float)
    peak = np.maximum.accumulate(eq)
    rets = np.diff(eq) / eq[:-1]
    rets = rets[np.isfinite(rets)]
    sharpe = (rets.mean() / rets.std() * np.sqrt(252)) if len(rets) > 1 and rets.std() > 0 else 0.0
    mdd = float(((eq - peak) / peak).min()) if len(eq) else 0.0

    tdf = pd.DataFrame(trades)
    return {
        'rule': rule, 'slots': slots, 'cap': cap_divisor, 'init': initial_cash,
        'final': final,
        'total_ret_pct': (final / initial_cash - 1) * 100,
        'n_trades': len(trades),
        'n_nocash': n_nocash,
        'nocash_pct': (n_nocash / n_attempt * 100) if n_attempt else 0.0,
        'sharpe': sharpe,
        'mdd_pct': mdd * 100,
        'avg_fill': float(np.mean(slot_fill)) if slot_fill else 0.0,
        'avg_util': float(np.mean(util)) * 100 if util else 0.0,
        'limit_use': float(np.mean(limit_use)) * 100 if limit_use else 0.0,
        'deploy_ratio': deploy_ratio,
        'avg_pos_won': tdf['spent'].mean() if len(tdf) else 0.0,
        'max_pos_won': tdf['spent'].max() if len(tdf) else 0.0,
        # 자금이 총상승률 높은 쪽(리스트 뒤쪽)으로 쏠리는지 보는 지표.
        # 금액가중이 단순평균보다 크면 정렬 편향이 생긴 것 = '높은순 매수'에 가까워진 것.
        'avg_total_rate': tdf['total_rate'].mean() if len(tdf) else 0.0,
        'wgt_total_rate': (np.average(tdf['total_rate'], weights=tdf['spent'])
                           if len(tdf) and tdf['spent'].sum() > 0 else 0.0),
        'trades_df': tdf,
    }


# ── 출력 ────────────────────────────────────────────────────────────────────
LABEL = {'current': '현행', 'A1': 'A-1순차', 'A2': 'A-2균등'}
HDR = (f'{"규칙":<8}{"슬롯":>5}{"상한":>6}{"총수익%":>9}{"Sharpe":>8}{"MDD%":>8}'
       f'{"체결":>7}{"nocash%":>8}{"체결/일":>8}{"활용도%":>8}'
       f'{"평균비중":>10}{"최대비중":>11}{"총상승":>8}{"가중":>8}')


def row(r):
    return (f'{LABEL[r["rule"]]:<8}{r["slots"]:>5}{(r["cap"] or "-"):>6}'
            f'{r["total_ret_pct"]:>9.1f}{r["sharpe"]:>8.2f}{r["mdd_pct"]:>8.1f}'
            f'{r["n_trades"]:>7}{r["nocash_pct"]:>8.1f}{r["avg_fill"]:>8.1f}'
            f'{r["avg_util"]:>8.1f}{r["avg_pos_won"]:>10,.0f}{r["max_pos_won"]:>11,.0f}'
            f'{r["avg_total_rate"]:>8.2f}{r["wgt_total_rate"]:>8.2f}')


def table(df, cap0, configs, title, cost=0.0):
    print('=' * 128)
    print(title)
    print('=' * 128)
    print(HDR)
    print('-' * 128)
    for rule, slots, cap in configs:
        print(row(simulate(df, cap0, rule, slots=slots, cap_divisor=cap, round_trip_cost=cost)))
    print()


MAIN_CONFIGS = [
    ('current', 20, None), ('A1', 20, None), ('A1', 20, 20), ('A1', 20, 12),
    ('A1', 20, 10), ('A1', 20, 8), ('A2', 20, None), ('A2', 20, 12),
    ('current', 13, None), ('current', 10, None),
]
SWEEP_CONFIGS = [('current', 20, None), ('A1', 20, 20), ('A1', 20, 12),
                 ('A1', 20, 10), ('A1', 20, 8)]


def mode_compare(df):
    for cap0 in [DEFAULT_CAPITAL, 10_000_000, 30_000_000]:
        table(df, cap0, MAIN_CONFIGS, f'초기자본 {cap0:,}원')
    table(df, DEFAULT_CAPITAL,
          [('current', 20, None), ('A1', 20, 20), ('A1', 20, 12), ('A1', 20, 8)],
          f'왕복비용 0.2% 반영 - 초기자본 {DEFAULT_CAPITAL:,}원', cost=0.002)


def mode_cap(df):
    cfgs = [(rule, 20, cap) for rule in ('A1', 'A2')
            for cap in (4, 6, 8, 10, 12, 16, 20, None)]
    table(df, DEFAULT_CAPITAL, [('current', 20, None)] + cfgs,
          f'종목당 상한 민감도 (초기자본 {DEFAULT_CAPITAL:,}원). 상한 = 매수한도 / divisor')


def mode_sweep(df):
    """계좌 규모 스윕 — '상한12가 좋은 게 계좌가 작아서인가'에 답하는 모드."""
    caps = [3_000_000, 5_000_000, 7_600_000, 10_000_000, 15_000_000,
            30_000_000, 50_000_000, 100_000_000, 300_000_000]
    names = ['현행20', '상한20', '상한12', '상한10', '상한8']
    store = {}
    for cap0 in caps:
        store[cap0] = {n: simulate(df, cap0, rule, slots=s, cap_divisor=c)
                       for n, (rule, s, c) in zip(names, SWEEP_CONFIGS)}

    print('=' * 108)
    print('계좌 규모별 총수익% (괄호=현행 대비 %p)')
    print('=' * 108)
    print(f'{"자본":>12}' + ''.join(f'{n:>18}' for n in names))
    print('-' * 108)
    for cap0 in caps:
        base = store[cap0]['현행20']['total_ret_pct']
        line = f'{cap0 / 1e6:>10.0f}M '
        for n in names:
            v = store[cap0][n]['total_ret_pct']
            line += f'{v:>10.1f}(  -  )' if n == '현행20' else f'{v:>10.1f}({v - base:+5.1f})'
        print(line)

    for key, label in [('nocash_pct', 'nocash% — 계좌가 커지면 사라지는 "규모 효과"'),
                       ('avg_util', '자본 활용도% — 규모와 무관한 "구조적 차이" (진짜 원인)')]:
        print(f'\n{label}')
        print(f'{"자본":>12}' + ''.join(f'{n:>10}' for n in names))
        print('-' * 62)
        for cap0 in caps:
            print(f'{cap0 / 1e6:>10.0f}M ' + ''.join(f'{store[cap0][n][key]:>10.1f}' for n in names))

    print('\nSharpe / MDD%')
    print(f'{"자본":>12}' + ''.join(f'{n:>16}' for n in names))
    print('-' * 92)
    for cap0 in caps:
        print(f'{cap0 / 1e6:>10.0f}M ' + ''.join(
            f'{store[cap0][n]["sharpe"]:>8.2f}{store[cap0][n]["mdd_pct"]:>8.1f}' for n in names))
    print()


def mode_periods(df):
    bounds = ['2025-12-31', '2026-03-31']
    b0, b1 = [pd.Timestamp(x).date() for x in bounds]
    subs = [('2025-09~2025-12', df[df['D'] <= b0]),
            ('2026-01~2026-03', df[(df['D'] > b0) & (df['D'] <= b1)]),
            ('2026-04~2026-07', df[df['D'] > b1])]
    cfgs = [('current', 20, None), ('A1', 20, 20), ('A1', 20, 12),
            ('A1', 20, 10), ('A1', 20, 8), ('A2', 20, 12)]
    for cap0 in [DEFAULT_CAPITAL, 30_000_000]:
        for name, sub in subs:
            table(df=sub, cap0=cap0, configs=cfgs,
                  title=f'[{name}] {len(sub)}건 / {sub["D"].nunique()}거래일 '
                        f'/ 초기자본 {cap0:,}원')


def mode_monthly(df):
    cols = {'현행슬롯20': ('current', 20, None), 'A-1상한20': ('A1', 20, 20),
            'A-1상한12': ('A1', 20, 12), 'A-1상한8': ('A1', 20, 8),
            'A-2상한12': ('A2', 20, 12)}
    out = {}
    for k, (rule, s, c) in cols.items():
        t = simulate(df, DEFAULT_CAPITAL, rule, slots=s, cap_divisor=c)['trades_df']
        t = t.copy()
        t['period'] = pd.to_datetime(t['date']).dt.to_period('M')
        out[k] = t.groupby('period').apply(lambda g: g['pnl'].sum() / DEFAULT_CAPITAL * 100)
    m = pd.DataFrame(out)
    print('=' * 128)
    print(f'월별 실현손익 (초기자본 {DEFAULT_CAPITAL:,}원 대비 %)')
    print('=' * 128)
    print(m.round(2).to_string())
    print('\n음수 월 개수:', {k: int((m[k] < 0).sum()) for k in m.columns})
    print()


def mode_mechanism(df):
    """상한20의 개선이 '재분배'가 아니라 '후보 많은 날 희석'임을 후보 수 구간별로 보여준다."""
    cand_per_day = df.groupby('D').size().rename('n_cand')
    print('=' * 128)
    print('상한20 개선의 정체: 후보 수 구간별 투입/손익')
    print('=' * 128)
    for name, r in [('현행', simulate(df, DEFAULT_CAPITAL, 'current', slots=20)),
                    ('A-1+상한20', simulate(df, DEFAULT_CAPITAL, 'A1', slots=20, cap_divisor=20))]:
        t = r['trades_df'].copy()
        t['date'] = pd.to_datetime(t['date']).dt.date
        t = t.join(cand_per_day, on='date')
        t['bucket'] = pd.cut(t['n_cand'], [0, 10, 20, 30, 70],
                             labels=['후보1-10', '후보11-20', '후보21-30', '후보31+'])
        g = t.groupby('bucket', observed=False).agg(
            체결=('spent', 'size'), 평균비중=('spent', 'mean'),
            총투입=('spent', 'sum'), 실현손익=('pnl', 'sum'))
        print(f'\n[{name}] 총수익 {r["total_ret_pct"]:.1f}% / Sharpe {r["sharpe"]:.2f} '
              f'/ MDD {r["mdd_pct"]:.1f}% / 활용도 {r["avg_util"]:.1f}%')
        print(g.round(0).to_string())
    print()


def mode_today(df=None):
    """2026-08-11 실매매 케이스에서 각 규칙이 실제로 얼마를 집행하는지."""
    prices = [165600, 107700, 256000, 75600, 210000, 237500, 10670, 14780, 63200,
              418000, 28450, 284500, 76700, 5610, 20650, 149600, 5880, 23650]
    limit = 2_625_514
    print('=' * 128)
    print(f'2026-08-11 실매매 케이스: 후보 {len(prices)}종목, 매수한도 {limit:,}원')
    print('=' * 128)
    for label, rule, cap in [('현행', 'current', None), ('A-1 상한20', 'A1', 20),
                             ('A-1 상한12', 'A1', 12), ('A-1 상한10', 'A1', 10),
                             ('A-1 상한8', 'A1', 8), ('A-1 상한없음', 'A1', None)]:
        deployed, n = 0.0, 0
        pos_cap = limit / cap if cap else float('inf')
        for k, p in enumerate(prices):
            if n >= BUY_SLOTS:
                break
            b = limit / BUY_SLOTS if rule == 'current' else (limit - deployed) / max(1, len(prices) - k)
            b = min(b, pos_cap, limit - deployed)
            q = int(b // p)
            if q > 0:
                deployed += q * p
                n += 1
        print(f'{label:<14}{n:>3}종목  {deployed:>10,.0f}원 집행 ({deployed / limit:>5.1%})  '
              f'미사용 {limit - deployed:>9,.0f}원')
    print()


def mode_ratio(df):
    """CASH_DEPLOY_RATIO(그날 남은 현금 중 쓸 비율)와 실제 보유 비율의 관계.

    코드의 70%는 '자산의 70%를 보유'가 아니라 '매일 남은 현금의 70%까지만 신규 매수'다.
    보유 기간이 평균 h일이면 정상상태 보유비율 u는
        u = h·r / (1 + h·r)      (r = deploy_ratio)
    로, h=2.28일이면 r=0.70에서 u는 약 61%가 이론적 상한이다. 70% 보유를 원하면 r을 1.0 근처로
    올려야 하는데 그건 '30% 현금 버퍼' 설계와 정면으로 충돌한다.
    아래 표는 그 이론값과 실측을 나란히 놓고, 현행 규칙이 한도조차 못 쓰고 있음을 보여준다.
    """
    h = df['days'].mean()
    print('=' * 128)
    print(f'CASH_DEPLOY_RATIO vs 실제 보유비율 (초기자본 {DEFAULT_CAPITAL:,}원, 평균보유 {h:.2f}일)')
    print('=' * 128)
    print('한도소진율 = 그날 집행액 / 그날 매수한도. 이게 100%가 아니면 의도한 만큼 못 쓰고 있는 것.')
    print(f'\n{"ratio":>7}{"규칙":>10}{"상한":>6}{"이론보유%":>10}{"실측보유%":>10}'
          f'{"한도소진%":>10}{"총수익%":>9}{"Sharpe":>8}{"MDD%":>8}{"nocash%":>8}')
    print('-' * 96)
    for r in [0.5, 0.7, 0.85, 1.0]:
        u_theory = h * r / (1 + h * r) * 100
        for label, rule, cap in [('현행', 'current', None), ('A-1', 'A1', 20),
                                 ('A-1', 'A1', 12)]:
            s = simulate(df, DEFAULT_CAPITAL, rule, slots=20, cap_divisor=cap, deploy_ratio=r)
            print(f'{r:>7.2f}{label:>10}{(cap or "-"):>6}{u_theory:>10.1f}{s["avg_util"]:>10.1f}'
                  f'{s["limit_use"]:>10.1f}{s["total_ret_pct"]:>9.1f}{s["sharpe"]:>8.2f}'
                  f'{s["mdd_pct"]:>8.1f}{s["nocash_pct"]:>8.1f}')
        print('-' * 96)
    print()


MODES = {'compare': mode_compare, 'cap': mode_cap, 'sweep': mode_sweep,
         'periods': mode_periods, 'monthly': mode_monthly,
         'mechanism': mode_mechanism, 'today': mode_today, 'ratio': mode_ratio}


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')   # 콘솔이 cp949면 한글이 깨진다
    except Exception:
        pass

    if len(sys.argv) < 2:
        print(__doc__)
        print(f'모드: {" ".join(MODES)} | all')
        return 1

    df = load(sys.argv[1])
    modes = sys.argv[2:] or ['compare']
    if 'all' in modes:
        modes = list(MODES)

    print(f'데이터: {len(df)}건 / {df["D"].nunique()}거래일 / {df["D"].min()} ~ {df["D"].max()}')
    print('(체결/일=일평균 체결종목수, 활용도=주식 원가/총자산 일평균, '
          '총상승/가중=total_rate 단순평균 vs 금액가중평균)\n')
    for m in modes:
        if m not in MODES:
            print(f'알 수 없는 모드: {m} (가능: {" ".join(MODES)} | all)')
            return 1
        MODES[m](df)
    return 0


if __name__ == '__main__':
    sys.exit(main())
