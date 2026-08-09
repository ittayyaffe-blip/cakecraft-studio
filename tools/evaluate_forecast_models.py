#!/usr/bin/env python
"""ONE-TIME model comparison for the Business Intelligence Layer's
forecasting pipeline. Not part of the deployed app — a standalone
analysis script, run locally, whose conclusion (which model to deploy)
is written up in docs/BUSINESS_INTELLIGENCE_LAYER.md and hard-coded into
the production `forecast_service.py`.

Trains Random Forest, XGBoost, LightGBM, and CatBoost on the same
engineered daily feature set built from the seeded historical orders,
evaluates each with a time-based train/test split (never random-shuffle
a time series), and prints a comparison table for order-volume and
revenue regression.

Requires the four comparison libraries installed locally
(`pip install scikit-learn xgboost lightgbm catboost`) — NOT in
requirements.txt, since only the winning model's library ships in
production (see "Deploy ONLY the selected model").

Usage (from anywhere, run with the project's venv):
    <venv>/python tools/evaluate_forecast_models.py
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, mean_squared_error

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.database import supabase  # noqa: E402


def _fetch_all_orders(columns: str) -> list[dict]:
    """Paginates past PostgREST's default max-rows response cap (1000) —
    the same fix already applied to forecast_service.py/dashboard_service.py/
    briefing_service.py (see forecast_service._fetch_order_history's own
    docstring for the full story). Without this, this comparison would
    silently train/test on an arbitrary ~1000-order subset instead of the
    full seeded history, undermining the one thing this script exists to
    guarantee: candidates evaluated on the *same* dataset.
    """
    rows: list[dict] = []
    page_size = 1000
    start = 0
    while True:
        response = supabase.table("orders").select(columns).range(start, start + page_size - 1).execute()
        rows.extend(response.data)
        if len(response.data) < page_size:
            break
        start += page_size
    return rows


def load_daily_series() -> pd.DataFrame:
    """One row per calendar day from the first order to today, with
    order_count/revenue (0 for days with no orders) plus the raw feature
    inputs needed downstream. Built from `orders.created_at`/`total_price`
    — the same source of truth forecast_service.py already reads.
    """
    rows = _fetch_all_orders("created_at, total_price, status, pickup_date")
    df = pd.DataFrame(rows)
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True, format="ISO8601")
    df["date"] = df["created_at"].dt.date

    daily = df.groupby("date").agg(order_count=("date", "size"), revenue=("total_price", "sum")).reset_index()

    full_range = pd.date_range(df["date"].min(), df["date"].max(), freq="D").date
    daily = daily.set_index("date").reindex(full_range, fill_value=0).rename_axis("date").reset_index()
    daily["revenue"] = daily["revenue"].astype(float)

    # Confirmed-orders-for-date signal, same one forecast_service.py's
    # heuristic model already uses as a deterministic floor.
    pickup_counts = (
        df[df["status"].isin(["confirmed", "in_progress", "ready"]) & df["pickup_date"].notna()]
        .groupby(df["pickup_date"])
        .size()
    )
    daily["date_str"] = daily["date"].astype(str)
    daily["confirmed_for_date"] = daily["date_str"].map(pickup_counts).fillna(0).astype(int)
    daily = daily.drop(columns=["date_str"])

    return daily


def build_features(daily: pd.DataFrame) -> pd.DataFrame:
    """Engineer the feature set every candidate model trains on:
    calendar signals (day of week, month, weekend), recent history (lags,
    rolling mean/std), a trend index, and the confirmed-orders signal.
    Target columns (order_count, revenue) are shifted so each row
    predicts the *next* day from features known as of the current day —
    exactly what forecast_service.py needs to predict tomorrow.
    """
    df = daily.copy()
    df["dow"] = pd.to_datetime(df["date"]).dt.weekday
    df["month"] = pd.to_datetime(df["date"]).dt.month
    df["is_weekend"] = df["dow"].isin([5, 6]).astype(int)
    df["day_index"] = np.arange(len(df))  # trend

    for lag in (1, 7, 14):
        df[f"lag_{lag}_count"] = df["order_count"].shift(lag)
        df[f"lag_{lag}_revenue"] = df["revenue"].shift(lag)

    df["roll7_mean_count"] = df["order_count"].shift(1).rolling(7).mean()
    df["roll7_std_count"] = df["order_count"].shift(1).rolling(7).std()
    df["roll28_mean_count"] = df["order_count"].shift(1).rolling(28).mean()
    df["roll7_mean_revenue"] = df["revenue"].shift(1).rolling(7).mean()
    df["roll28_mean_revenue"] = df["revenue"].shift(1).rolling(28).mean()

    # confirmed_for_date describes THAT day's known pickups, which is
    # legitimately known in advance (orders get confirmed ahead of their
    # pickup date) — not a leak, this is the real "already on the books"
    # signal available at prediction time.
    df["target_count"] = df["order_count"]
    df["target_revenue"] = df["revenue"]

    df = df.dropna().reset_index(drop=True)
    return df


FEATURE_COLUMNS = [
    "dow", "month", "is_weekend", "day_index", "confirmed_for_date",
    "lag_1_count", "lag_7_count", "lag_14_count",
    "lag_1_revenue", "lag_7_revenue", "lag_14_revenue",
    "roll7_mean_count", "roll7_std_count", "roll28_mean_count",
    "roll7_mean_revenue", "roll28_mean_revenue",
]


def time_split(df: pd.DataFrame, test_fraction: float = 0.2):
    split_at = int(len(df) * (1 - test_fraction))
    return df.iloc[:split_at], df.iloc[split_at:]


def evaluate(name: str, model_factory, X_train, y_train, X_test, y_test) -> dict:
    model = model_factory()
    model.fit(X_train, y_train)
    preds = model.predict(X_test)

    # MAPE is undefined/explosive on days with zero actual orders (a
    # real, common case for this dataset) — score it only over the
    # nonzero-actual subset, purely as a supplementary sanity check
    # alongside MAE/RMSE (the metrics actually used to pick the winner).
    nonzero = y_test != 0
    mape = mean_absolute_percentage_error(y_test[nonzero], preds[nonzero]) if nonzero.any() else float("nan")

    return {
        "model": name,
        "mae": mean_absolute_error(y_test, preds),
        "rmse": mean_squared_error(y_test, preds) ** 0.5,
        "mape": mape,
    }


def get_candidates():
    """Each candidate's install status is checked at import time so a
    missing library degrades to "skipped, not installed" instead of
    crashing the whole comparison — useful since these are deliberately
    NOT permanent dependencies."""
    candidates = {}

    candidates["RandomForest"] = lambda: RandomForestRegressor(
        n_estimators=200, max_depth=6, min_samples_leaf=3, random_state=42
    )

    try:
        from xgboost import XGBRegressor

        candidates["XGBoost"] = lambda: XGBRegressor(
            n_estimators=200, max_depth=4, learning_rate=0.05, random_state=42, verbosity=0
        )
    except ImportError:
        print("XGBoost not installed — skipped.")

    try:
        from lightgbm import LGBMRegressor

        candidates["LightGBM"] = lambda: LGBMRegressor(
            n_estimators=200, max_depth=4, learning_rate=0.05, random_state=42, verbosity=-1, min_child_samples=5
        )
    except ImportError:
        print("LightGBM not installed — skipped.")

    try:
        from catboost import CatBoostRegressor

        candidates["CatBoost"] = lambda: CatBoostRegressor(
            iterations=200, depth=4, learning_rate=0.05, random_state=42, verbose=False
        )
    except ImportError:
        print("CatBoost not installed — skipped.")

    return candidates


def main():
    print("Loading and engineering features from live seeded order history...")
    daily = load_daily_series()
    df = build_features(daily)
    print(f"  {len(daily)} calendar days -> {len(df)} usable rows after lag/rolling warm-up.\n")

    train, test = time_split(df)
    print(f"Time-based split: {len(train)} train days, {len(test)} test days (most recent).\n")

    X_train, X_test = train[FEATURE_COLUMNS], test[FEATURE_COLUMNS]
    candidates = get_candidates()

    results = []
    for target, label in [("target_count", "Order Volume"), ("target_revenue", "Revenue")]:
        y_train, y_test = train[target], test[target]
        print(f"=== {label} ===")
        for name, factory in candidates.items():
            r = evaluate(name, factory, X_train, y_train, X_test, y_test)
            r["target"] = label
            results.append(r)
            print(f"  {name:14s}  MAE={r['mae']:6.2f}  RMSE={r['rmse']:6.2f}  MAPE={r['mape']:.1%}")
        print()

    return results


if __name__ == "__main__":
    main()
