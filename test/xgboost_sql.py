import os
import joblib
import pandas as pd

from sqlalchemy import create_engine
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, classification_report
from sqlalchemy.engine import URL


# =========================
# 1) DB 연결
# =========================
# 예) postgresql://user:password@host:5432/dbname
# DB_URL = os.environ.get("DB_URL", "postgresql+psycopg://chick:dlsdn317!@localhost:5432/mydb")

import os
from sqlalchemy.engine import URL

DB_URL = URL.create(
    "postgresql+psycopg",
    username=os.environ["DB_USERNAME"],
    password=os.environ["DB_PASSWORD"],
    host=os.environ["DB_HOST"],
    port=5432,
    database=os.environ["DB_NAME"],
)

engine = create_engine(DB_URL, connect_args={"options": "-c client_encoding=UTF8"})


# =========================
# 2) 학습용 데이터 쿼리
# =========================
# 여기서 만들어야 하는 컬럼:
# - anchor_date: 신호 기준일(날짜)
# - feature들: avg_change_pct, increase_per_day, avg_trading_value, market_value, cnt, total_rate_of_increase 등
# - label: success (0/1) => "신호 이후 5거래일 중 3회 이상 interest_stocks에 등장하면 1"
#
# 아래 SQL은 "샘플 템플릿"입니다.
# 당신의 기존 '급등 신호 요약' 로직을 signal CTE 안에 넣고,
# future(미래 5거래일 등장 횟수)로 label을 만듭니다.

TRAIN_SQL = """
WITH params AS (
  SELECT
    (CURRENT_DATE - INTERVAL '60 days')::date AS start_date,
    (CURRENT_DATE - INTERVAL '6 days')::date  AS end_date
),
anchors AS (
  -- 최근 2달 동안, 하루씩 anchor_date 생성 (너무 최신(미래 5거래일이 아직 안 생긴 구간)은 제외)
  SELECT generate_series(p.start_date, p.end_date, interval '1 day')::date AS anchor_date
  FROM params p
),

-- 1) anchor_date 기준 "과거 14일" 급등 신호 요약
signal AS (
  SELECT
    a.anchor_date,
    is2.stock_code,
    is2.stock_name,
    COUNT(*) AS cnt,
    ROUND(AVG(is2.today_price_change_pct::numeric), 3) AS avg_change_pct,
    ROUND(
      100.0 * (COALESCE(MAX(is2.last_close::numeric), 0) - MIN(is2.current_price::numeric))
      / NULLIF(MIN(is2.current_price::numeric), 0),
      3
    ) AS total_rate_of_increase,
    ROUND(
      100.0 * (COALESCE(MAX(is2.last_close::numeric), 0) - MIN(is2.current_price::numeric))
      / NULLIF(MIN(is2.current_price::numeric), 0) / COUNT(*),
      3
    ) AS increase_per_day,
    AVG(is2.current_trading_value::numeric) AS avg_trading_value,
    MAX(is2.market_value::numeric) AS market_value,
    MAX(is2.created_at) AS signal_ts
  FROM anchors a
  JOIN interest_stocks is2
    ON is2.created_at >= a.anchor_date - INTERVAL '14 days'
   AND is2.created_at <  a.anchor_date + INTERVAL '1 day'
  WHERE is2.market_value::numeric > 50000000000
    AND is2.current_trading_value::numeric > 7000000000
    AND is2.today_price_change_pct IS NOT NULL
  GROUP BY a.anchor_date, is2.stock_code, is2.stock_name
  HAVING COUNT(*) > 1
),

-- 2) 기존 필터(당신이 쓰던 threshold)
filtered AS (
  SELECT *
  FROM signal
  WHERE avg_change_pct > 5.7
    AND total_rate_of_increase > 10
    AND increase_per_day > 3.5
),

-- 3) "미래 5거래일 중 3번 이상 등장" 라벨 만들기
-- interest_stocks는 이벤트(5퍼센트↑) 발생일만 들어오므로,
-- "미래 window에서 몇 번 insert 되었는가"가 곧 성공 판단 기준.
future_hits AS (
  SELECT
    f.anchor_date,
    f.stock_code,
    COUNT(*) AS hits_5d
  FROM filtered f
  JOIN interest_stocks i
    ON i.stock_code = f.stock_code
   AND i.created_at > f.signal_ts
   AND i.created_at <= f.signal_ts + INTERVAL '10 days'
  GROUP BY f.anchor_date, f.stock_code
)

SELECT
  f.anchor_date,
  f.stock_code,
  f.stock_name,
  f.cnt,
  f.avg_change_pct,
  f.total_rate_of_increase,
  f.increase_per_day,
  f.avg_trading_value,
  f.market_value,
  COALESCE(h.hits_5d, 0) AS hits_5d,
  CASE WHEN COALESCE(h.hits_5d, 0) >= 3 THEN 1 ELSE 0 END AS success
FROM filtered f
LEFT JOIN future_hits h
  ON h.anchor_date = f.anchor_date
 AND h.stock_code = f.stock_code
;
"""


# =========================
# 3) 데이터 로드 + 전처리
# =========================
def load_train_df():
    df = pd.read_sql(TRAIN_SQL, engine)
    print(df)

    # 기본 sanity check
    if df.empty:
        raise RuntimeError("학습 데이터가 비었습니다. (필터/기간/데이터 수집 상태 확인 필요)")

    # feature 목록
    feature_cols = [
        "cnt",
        "avg_change_pct",
        "total_rate_of_increase",
        "increase_per_day",
        "avg_trading_value",
        "market_value",
        # 필요하면 pred_price_change_3d_pct 같은 컬럼도 signal 쿼리에 포함해서 여기 추가
    ]

    # 숫자형 강제 변환(혹시 문자열로 들어오면 NaN 처리)
    for c in feature_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["success"] = pd.to_numeric(df["success"], errors="coerce").fillna(0).astype(int)

    # 날짜 기준 정렬(시계열 분리할 때 유리)
    df = df.sort_values(["anchor_date", "stock_code"]).reset_index(drop=True)
    return df, feature_cols


# =========================
# 4) 모델 학습
# =========================
def train_logistic(df, feature_cols):
    X = df[feature_cols]
    y = df["success"]

    # 시계열이면 랜덤 split보다 날짜 기준 split이 더 안전합니다.
    # 여기서는 간단히 80/20 분리(실무에선 anchor_date로 cutoff 추천).
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y if y.nunique() > 1 else None
    )

    pipe = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(
            max_iter=2000,
            class_weight="balanced",   # ✅ 희귀 이벤트(1이 적음) 대응
            solver="lbfgs"
        )),
    ])

    pipe.fit(X_train, y_train)

    # 확률 예측
    proba = pipe.predict_proba(X_test)[:, 1]

    # 평가(1이 너무 적으면 AUC가 NaN/의미 없을 수 있음)
    try:
        auc = roc_auc_score(y_test, proba)
        print(f"[AUC] {auc:.4f}")
    except Exception:
        print("[AUC] 계산 불가(테스트셋에 클래스가 한쪽만 있거나 표본이 너무 적음)")

    preds = (proba >= 0.5).astype(int)
    print(classification_report(y_test, preds, digits=4))

    # 계수(피처 중요도 느낌: 절댓값이 클수록 영향 큼)
    clf = pipe.named_steps["clf"]
    coef = pd.Series(clf.coef_[0], index=feature_cols).sort_values(key=lambda s: s.abs(), ascending=False)
    print("\n[Logistic Coefficients | abs desc]")
    print(coef)

    return pipe


# =========================
# 5) 저장 + 스코어링 예시
# =========================
def save_model(model, path="interest_signal_lr.joblib"):
    joblib.dump(model, path)
    print(f"[saved] {path}")


def main():
    df, feature_cols = load_train_df()

    # 라벨 분포 확인
    print(df["success"].value_counts(dropna=False))
    print(f"success_rate={df['success'].mean():.4f} (1 비율)")

    model = train_logistic(df, feature_cols)
    save_model(model)


if __name__ == "__main__":
    main()

'''
success
0    2161
1     355
Name: count, dtype: int64
success_rate=0.1411 (1 비율)
[AUC] 0.6903
              precision    recall  f1-score   support

           0     0.9044    0.7644    0.8285       433
           1     0.2609    0.5070    0.3445        71

    accuracy                         0.7282       504
   macro avg     0.5826    0.6357    0.5865       504
weighted avg     0.8137    0.7282    0.7603       504


[Logistic Coefficients | abs desc]
total_rate_of_increase    1.260904
increase_per_day         -0.852330
market_value             -0.829449
avg_trading_value        -0.209763
cnt                      -0.177163
avg_change_pct           -0.005535
dtype: float64

'''
