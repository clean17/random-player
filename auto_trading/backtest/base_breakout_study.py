# -*- coding: utf-8 -*-
"""'하락 → 바닥 다지기 → 재상승' 베이스 돌파 전략 탐색 (2026-08-19 작성).

━━━ 왜 새 연구인가 (기존 기각된 것과 다른 점) ━━━
  rebound_signal.py  : '급락 후 첫 반등일' 매수 → 평균 +0.417%지만 중앙 -0.837%, P(-5%↓) 65.9%. 기각.
  deadcat_filter.py  : '반등 지속 확인 후' 매수 → 확인을 기다리면 성과가 단조 감소. 기각.
  wave_analysis.py   : '급락 + 오늘도 하락'이 5일 평균 최고(+1.215%)지만 하방이 감당 불가.
  → 셋 다 **급락 직후의 방향 전환**을 잡으려 했다.

  이 스크립트는 다르다: **변동성이 수축하고 신저가가 사라진 '베이스'** 를 찾는다.
  하락이 끝났는지를 반등의 유무가 아니라 **더 이상 내려가지 않는다는 사실**로 판정한다.

━━━ 베이스 정의 (파라미터) ━━━
  1) 선행 하락   : 종가가 LOOK(60)일 고점 대비 DD_MIN 이상 하락한 상태
  2) 다지기      : 최근 BASE일 구간에서
       - 신저가 소멸 : 그 구간 최저가 > 직전 BASE일 구간 최저가
       - 박스 수축   : (구간 고가/구간 저가 - 1) <= BOX_MAX
       - 변동성 수축 : 구간말 ATR/종가 <= 구간초 ATR/종가 * VC_MAX
  3) 돌파 트리거 : breakout = 종가가 직전 BASE일 고가를 상향 돌파
                   ma20     = 종가가 MA20 위로 회복(전일은 아래)

━━━ 위생 규칙 (이번 세션에서 데인 것들) ━━━
  - **상한가 제외**: 등락률 >= 28% 또는 (종가위치>=0.99 & 등락률>=15%) → 종가 매수 불가
  - 거래대금 >= 20억, 종가 >= 700원 (체결 가능성)
  - pkl 0원 불량행 제외
  - **시간 분할 walk-forward**: 훈련 2023-03~2024-12 / 시험 2025-01~2026-08.
    훈련에서 조합을 고르고 시험에서만 판정한다. 시험 성적이 곧 결론이다.
  - 조합 수를 로그로 남긴다(다중비교 편향을 숨기지 않기 위해)
  - 건당 기대수익과 포트폴리오 CAGR을 같이 낸다 — 건당 +0.07%가 CAGR -9%가 되는 것을
    이미 겪었다(limitup_recheck.py). 변동성 끌림 때문에 건당만으로는 판단할 수 없다.

사용법:
    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe auto_trading/backtest/base_breakout_study.py
    ... --limit 400          (빠른 확인)
    ... --stage exit         (승자 진입안에 청산 스윕)
"""
import argparse
import itertools
import os
import sys
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from auto_trading.kiwoom_fire_strategy_mock import PKL_DIR                # noqa: E402
from auto_trading.backtest.cash_ratio_test import simulate           # noqa: E402

MIN_TV = 2_000_000_000
MIN_CLOSE = 700
LOOK = 120               # 선행 하락 판정 기간(고점 탐색 창).
                         # 60일로 잡으면 베이스가 20~30일 길어질 때 그 고점이 창에서 빠져나가
                         # 낙폭이 저절로 사라진다(실측: base=30 & -30%가 종목당 1건). 120일로 늘려
                         # '하락 후 다지기' 상태가 창 안에 함께 남게 한다.
COST = 0.2               # % 왕복비용
SPLIT = pd.Timestamp('2025-01-01')

# 진입 파라미터 격자
DD_MINS = (-0.10, -0.20, -0.30)   # LOOK일 고점 대비 낙폭
BASES = (10, 15, 20)              # 다지기 기간
BOX_MAXS = (0.15, 0.25, 0.40)     # 다지기 박스 폭 상한
VC_MAXS = (0.90, 1.20)            # 변동성 수축 배수 (1.20 = 사실상 요구 안 함)
TRIGGERS = ('breakout', 'ma20')

# 기본 청산 (진입 선정 단계에서 고정)
DEF_STOP, DEF_HOLD = -0.08, 10


def prep(path):
    try:
        df = pd.read_pickle(path)
    except Exception:
        return None
    need = ['시가', '고가', '저가', '종가', '거래량', '등락률']
    if not all(c in df.columns for c in need):
        return None
    df = df[need].dropna()
    df = df[(df[['시가', '고가', '저가', '종가']] > 0).all(axis=1)]
    if len(df) < LOOK + 80:
        return None
    df.index = pd.to_datetime(df.index)

    c = df['종가'].astype(float)
    h = df['고가'].astype(float)
    l = df['저가'].astype(float)
    o = df['시가'].astype(float)
    chg = df['등락률'].astype(float)
    tv = df['거래량'].astype(float) * c

    prev = c.shift(1)
    tr = np.maximum(h - l, np.maximum((h - prev).abs(), (l - prev).abs()))
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    cpos = np.where(h > l, (c - l) / (h - l), 1.0)

    return {
        'idx': df.index, 'o': o.to_numpy(), 'h': h.to_numpy(), 'l': l.to_numpy(),
        'c': c.to_numpy(), 'chg': chg.to_numpy(), 'tv': tv.to_numpy(),
        'atr': atr.to_numpy(), 'cpos': cpos,
        'ma20': c.rolling(20).mean().to_numpy(),
        # 상한가 등 종가 매수 불가 판정
        'unbuyable': ((chg >= 28) | ((cpos >= 0.99) & (chg >= 15))).to_numpy(),
        'c_s': c, 'h_s': h, 'l_s': l,
        'volr_s': atr / c,                       # ATR/종가 (변동성 비율)
        'hi60_s': c.rolling(LOOK).max(),
    }


def signals(d, dd_min, base, box_max, vc_max, trigger) -> np.ndarray:
    """베이스 조건을 만족하는 인덱스 배열.

    ★ 베이스 통계는 모두 '어제까지'(shift(1)) 기준이다. 돌파일 자체를 베이스에 넣으면
      돌파(고변동성)와 '변동성 수축' 조건이 서로 모순돼 교집합이 사라진다
      (실측: 484종목에서 11건). 베이스가 먼저 형성되고 그 다음 돌파가 오는 구조로 맞춘다.
    """
    c = d['c']
    n = len(c)
    base_hi = d['h_s'].shift(1).rolling(base).max().to_numpy()      # 베이스 고가(어제까지)
    base_lo = d['l_s'].shift(1).rolling(base).min().to_numpy()      # 베이스 저가
    prev_lo = d['l_s'].shift(1 + base).rolling(base).min().to_numpy()  # 그 직전 구간 저가
    box = base_hi / base_lo - 1
    vol_end = d['volr_s'].shift(1).to_numpy()                       # 베이스 끝 변동성
    vol_start = d['volr_s'].shift(1 + base).to_numpy()              # 베이스 시작 변동성
    dd_base = (d['c_s'].shift(1) / d['hi60_s'].shift(1) - 1).to_numpy()  # 베이스 시점 낙폭

    ok = (
        (d['tv'] >= MIN_TV) & (c >= MIN_CLOSE) & ~d['unbuyable']
        & (dd_base <= dd_min)                    # 선행 하락 (베이스 시점)
        & (base_lo > prev_lo)                    # 신저가 소멸
        & (box <= box_max)                       # 박스 수축
        & (vol_end <= vol_start * vc_max)         # 변동성 수축
        & np.isfinite(prev_lo) & np.isfinite(vol_start) & np.isfinite(dd_base)
        & np.isfinite(d['ma20'])
    )
    if trigger == 'breakout':
        ok = ok & (c > base_hi)                  # 종가가 베이스 상단 돌파
    else:                                        # MA20 회복
        ok = ok & (c > d['ma20']) & (np.r_[np.nan, c[:-1]] <= np.r_[np.nan, d['ma20'][:-1]])
    ok[:LOOK + base * 2 + 2] = False
    ok[n - 1:] = False
    return np.flatnonzero(ok)


def exits(d, idxs, stop, hold):
    """손절 stop(장중 저가) 또는 hold일차 개장가 청산. (ret%, 보유일) 리스트."""
    c, l, op = d['c'], d['l'], d['o']
    out = []
    for i in idxs:
        e = c[i]
        if i + hold >= len(c):
            continue
        r, hd = None, hold
        for k in range(1, hold):
            if l[i + k] / e - 1 <= stop:
                r, hd = stop * 100, k
                break
        if r is None:
            r = (op[i + hold] / e - 1) * 100
        out.append((d['idx'][i], e, d['cpos'][i], r, hd))
    return out


def load(limit: Optional[int] = None):
    files = [f for f in os.listdir(PKL_DIR) if f.endswith('.pkl')]
    if limit:
        files = files[:limit]
    store = {}
    print(f'pkl 스캔 {len(files)}종목...', flush=True)
    for n, f in enumerate(files, 1):
        if n % 500 == 0:
            print(f'  ... {n}/{len(files)}', flush=True)
        d = prep(os.path.join(PKL_DIR, f))
        if d is not None:
            store[f[:-4]] = d
    return store


def collect(store, combo, stop=DEF_STOP, hold=DEF_HOLD) -> pd.DataFrame:
    dd, base, box, vc, trig = combo
    rows = []
    for code, d in store.items():
        idxs = signals(d, dd, base, box, vc, trig)
        if len(idxs) == 0:
            continue
        for D, e, cp, r, hd in exits(d, idxs, stop, hold):
            rows.append({'D': D, 'code': code, 'entry': e, 'close_pos': cp,
                         'ret': r, 'hold': hd})
    return pd.DataFrame(rows)


def stat(X):
    if len(X) == 0:
        return None
    return {'n': len(X), 'exp': X['ret'].mean() - COST,
            'med': X['ret'].median(), 'win': (X['ret'] > 0).mean() * 100}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--capital', type=int, default=1_990_000)
    ap.add_argument('--iters', type=int, default=20)
    args = ap.parse_args()

    store = load(args.limit)
    print(f'유효 {len(store)}종목\n')

    combos = list(itertools.product(DD_MINS, BASES, BOX_MAXS, VC_MAXS, TRIGGERS))
    print(f'진입 조합 {len(combos)}개 탐색 (청산 고정: 손절 {DEF_STOP:.0%} / {DEF_HOLD}일)')
    print('※ 훈련에서 고르고 시험에서 판정한다. 조합 수가 많을수록 훈련 1위는 운일 확률이 높다.\n')

    res = []
    for k, combo in enumerate(combos, 1):
        X = collect(store, combo)
        if len(X) == 0:
            continue
        tr, te = X[X['D'] < SPLIT], X[X['D'] >= SPLIT]
        s_tr, s_te = stat(tr), stat(te)
        if s_tr is None or s_te is None or s_tr['n'] < 150 or s_te['n'] < 100:
            continue
        res.append({'combo': combo, 'X': X, 'tr': s_tr, 'te': s_te})
        print(f'  [{k:>2}/{len(combos)}] {combo}  훈련 {s_tr["n"]:>5,}건 {s_tr["exp"]:+.3f}%  '
              f'시험 {s_te["n"]:>5,}건 {s_te["exp"]:+.3f}%', flush=True)

    if not res:
        print('\n표본 조건을 만족하는 조합이 없다.')
        return

    print(f'\n표본 충족 조합 {len(res)}개')
    res.sort(key=lambda r: -r['tr']['exp'])

    print('\n' + '=' * 104)
    print('훈련 기대수익 상위 10 — 시험 성적이 따라오는지 본다')
    print('=' * 104)
    print(f'{"낙폭":>6}{"베이스":>7}{"박스":>6}{"수축":>6}{"트리거":>10}'
          f'{"훈련건수":>9}{"훈련%":>9}{"시험건수":>9}{"시험%":>9}{"시험중앙":>9}{"시험승률":>9}')
    print('-' * 104)
    for r in res[:10]:
        dd, base, box, vc, trig = r['combo']
        print(f'{dd:>6.0%}{base:>7}{box:>6.0%}{vc:>6.2f}{trig:>10}'
              f'{r["tr"]["n"]:>9,}{r["tr"]["exp"]:>9.3f}'
              f'{r["te"]["n"]:>9,}{r["te"]["exp"]:>9.3f}'
              f'{r["te"]["med"]:>9.3f}{r["te"]["win"]:>8.1f}%')

    # 훈련 1위의 시험 성적 + 전체 조합의 훈련/시험 상관 — 과적합 진단
    tr_v = np.array([r['tr']['exp'] for r in res])
    te_v = np.array([r['te']['exp'] for r in res])
    print(f'\n훈련-시험 상관계수 {np.corrcoef(tr_v, te_v)[0, 1]:+.2f} '
          f'(0 근처면 훈련 성적이 시험을 예측하지 못한다 = 과적합)')
    print(f'시험 기대수익 플러스 조합: {(te_v > 0).sum()}/{len(res)}개')

    # 시험 기준 최고 조합으로 청산 스윕 + 포트폴리오
    best = max(res, key=lambda r: r['te']['exp'])
    print(f'\n시험 최고 조합: {best["combo"]}  시험 {best["te"]["exp"]:+.3f}%')

    print('\n' + '=' * 88)
    print(f'청산 스윕 (진입 = 시험 최고 조합, 시험구간만)')
    print('=' * 88)
    print(f'{"손절":>7}{"보유일":>7}{"건수":>9}{"기대수익%":>11}{"중앙%":>9}{"승률":>8}{"평균보유":>9}')
    print('-' * 88)
    grid = []
    for stop in (-0.06, -0.08, -0.12):
        for hold in (5, 10, 20):
            X = collect(store, best['combo'], stop, hold)
            te = X[X['D'] >= SPLIT]
            s = stat(te)
            if s is None or s['n'] < 200:
                continue
            grid.append((s['exp'], stop, hold, X, s, te['hold'].mean()))
            print(f'{stop:>7.0%}{hold:>7}{s["n"]:>9,}{s["exp"]:>11.3f}'
                  f'{s["med"]:>9.3f}{s["win"]:>7.1f}%{te["hold"].mean():>9.2f}')
    print()

    if not grid:
        return
    grid.sort(key=lambda g: -g[0])
    _, bstop, bhold, BX, bs, _ = grid[0]
    print(f'최고 청산: 손절 {bstop:.0%} / {bhold}일  → 시험 건당 {bs["exp"]:+.3f}%\n')

    # 포트폴리오 CAGR (시험구간)
    C = BX[BX['D'] >= SPLIT][['D', 'entry', 'close_pos', 'ret', 'hold']].copy()
    years = (C['D'].max() - C['D'].min()).days / 365.25
    per_day = C.groupby('D').size()
    print('=' * 88)
    print(f'포트폴리오 CAGR (시험구간 {years:.2f}년, 하루 평균 후보 {per_day.mean():.1f}종목, '
          f'{args.iters}회 부트)')
    print('=' * 88)
    print(f'{"ratio":>7}{"슬롯":>6}{"보유%":>8}{"부트 총수익":>13}{"CAGR":>9}'
          f'{"CAGR범위":>19}{"음수":>7}{"MDD%":>8}')
    print('-' * 88)
    rng = np.random.default_rng(20260819)
    for ratio, slots in ((0.30, 5), (0.50, 5), (0.65, 5), (0.65, 10), (0.90, 10)):
        s = simulate(C, args.capital, slots, slots, ratio, False, None)
        tot, ut = [], []
        for _ in range(args.iters):
            sub = C.groupby('D', group_keys=False).apply(
                lambda g: g.sample(max(1, int(len(g) * 0.8)),
                                   random_state=int(rng.integers(1 << 31))))
            o = simulate(sub, args.capital, slots, slots, ratio, False, None)
            tot.append(o['total']); ut.append(o['util'])
        tot = np.array(tot)
        cg = np.array([((1 + t / 100) ** (1 / years) - 1) * 100 if t > -100 else -99.9
                       for t in tot])
        print(f'{ratio:>7.2f}{slots:>6}{np.mean(ut):>8.1f}{tot.mean():>12.1f}%'
              f'{cg.mean():>8.1f}%{f"{cg.min():.1f} ~ {cg.max():.1f}%":>19}'
              f'{(tot < 0).mean() * 100:>6.0f}%{s["mdd"]:>8.1f}')
    print()


if __name__ == '__main__':
    main()
