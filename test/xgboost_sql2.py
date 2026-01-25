import os
import joblib
import pandas as pd
import xgboost as xgb

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, average_precision_score, classification_report
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from xgboost import XGBClassifier


# =========================
# 1) DB 연결
# =========================
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
# 2) 학습용 데이터 SQL
# =========================
TRAIN_SQL = """
WITH params AS (
  SELECT
    (CURRENT_DATE - INTERVAL '60 days')::date AS start_date,
    (CURRENT_DATE - INTERVAL '6 days')::date  AS end_date
),
anchors AS (
  SELECT generate_series(p.start_date, p.end_date, interval '1 day')::date AS anchor_date
  FROM params p
),
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
filtered AS (
  SELECT *
  FROM signal
  WHERE avg_change_pct > 5.7
    AND total_rate_of_increase > 10
    AND increase_per_day > 3.5
),
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


FEATURE_COLS = [
    "cnt",
    "avg_change_pct",
    "total_rate_of_increase",
    "increase_per_day",
    "avg_trading_value",
    "market_value",
]


def load_train_df():
    df = pd.read_sql(TRAIN_SQL, engine)
    if df.empty:
        raise RuntimeError("학습 데이터가 비었습니다. (기간/필터/수집 상태 확인)")

    for c in FEATURE_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["success"] = pd.to_numeric(df["success"], errors="coerce").fillna(0).astype(int)
    df["anchor_date"] = pd.to_datetime(df["anchor_date"])

    df = df.sort_values(["anchor_date", "stock_code"]).reset_index(drop=True)
    return df


def time_split(df, test_days=14):
    """최근 test_days를 테스트로 분리(시계열 누수 방지)"""
    cutoff = df["anchor_date"].max() - pd.Timedelta(days=test_days)
    train_df = df[df["anchor_date"] <= cutoff].copy()
    test_df = df[df["anchor_date"] > cutoff].copy()

    # 테스트가 너무 작으면 fallback
    if len(test_df) < 200 or train_df["success"].nunique() < 2:
        X = df[FEATURE_COLS]
        y = df["success"]
        return train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    X_train = train_df[FEATURE_COLS]
    y_train = train_df["success"]
    X_test = test_df[FEATURE_COLS]
    y_test = test_df["success"]
    return X_train, X_test, y_train, y_test


def train_xgboost(df):
    X_train, X_test, y_train, y_test = time_split(df, test_days=14)

    # 불균형 가중치: 0/1 비율로 자동 계산
    n_pos = int((y_train == 1).sum())
    n_neg = int((y_train == 0).sum())
    if n_pos == 0:
        raise RuntimeError("훈련 데이터에 success=1 이 없습니다. 라벨/기간 조정 필요.")
    scale_pos_weight = n_neg / n_pos

    # 결측치 처리(중앙값) 파이프라인
    imputer = SimpleImputer(strategy="median")
    X_train_imp = imputer.fit_transform(X_train)
    X_test_imp = imputer.transform(X_test)

    model = XGBClassifier(
        n_estimators=800,
        learning_rate=0.05,
        max_depth=4,
        min_child_weight=2,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        reg_alpha=0.0,
        gamma=0.0,
        scale_pos_weight=scale_pos_weight,
        objective="binary:logistic",
        eval_metric="aucpr",   # 희귀 이벤트엔 AUC-PR도 중요
        tree_method="hist",
        random_state=42,
    )

    # early stopping(검증셋)
    # model.fit(
    #     X_train_imp, y_train,
    #     eval_set=[(X_test_imp, y_test)],
    #     verbose=False,
    #     callbacks=[xgb.callback.EarlyStopping(rounds=50, save_best=True)]
    # )
    model.fit(X_train_imp, y_train)

    proba = model.predict_proba(X_test_imp)[:, 1]

    auc = roc_auc_score(y_test, proba) if y_test.nunique() == 2 else None
    ap = average_precision_score(y_test, proba) if y_test.nunique() == 2 else None

    print(f"[train] pos={n_pos}, neg={n_neg}, scale_pos_weight={scale_pos_weight:.3f}")
    if auc is not None:
        print(f"[AUC] {auc:.4f}")
    if ap is not None:
        print(f"[AUPRC] {ap:.4f}")

    # 기본 0.5 컷은 실전에선 별로라, 일단 리포트용으로만 출력
    preds = (proba >= 0.5).astype(int)
    print(classification_report(y_test, preds, digits=4))

    # feature importance (gain 기반)
    importances = pd.Series(model.feature_importances_, index=FEATURE_COLS).sort_values(ascending=False)
    print("\n[Feature Importances (XGBoost)]")
    print(importances)

    # 저장용: imputer + model 함께 묶기
    bundle = {
        "imputer": imputer,
        "model": model,
        "feature_cols": FEATURE_COLS,
    }
    return bundle


def save_bundle(bundle, path="interest_signal_xgb.joblib"):
    joblib.dump(bundle, path)
    print(f"[saved] {path}")


def main():
    df = load_train_df()
    print(df["success"].value_counts(dropna=False))
    print(f"success_rate={df['success'].mean():.4f} (1 비율)")

    bundle = train_xgboost(df)
    save_bundle(bundle)


if __name__ == "__main__":
    main()
