"""Dependency-free self-check for the pure logic in
`app.services.forecast_service` — no network/DB required (the feature
table and tomorrow-row builders take plain order dicts, not a live
query). Run from `backend/`:

    python -m tests.test_forecast_service

`compute_tomorrow_forecast` itself (which fetches from Supabase and
trains the Random Forest) is exercised live via `TestClient`/the real
`/admin/briefing` endpoint instead — see
docs/BUSINESS_INTELLIGENCE_LAYER.md. Everything below is the feature
engineering and explainability logic, fully offline and deterministic.
"""

from datetime import date, timedelta

import numpy as np

from app.services.forecast_service import (
    FEATURE_COLUMNS,
    _build_daily_feature_table,
    _build_reason,
    _confidence_from_trees,
    _tomorrow_feature_row,
    _workload_level,
)


def _fake_orders(n_days: int = 40, per_day: int = 2) -> list[dict]:
    """A small, synthetic order history: `per_day` orders on each of the
    last `n_days` days, all `completed`, no pickup_date — enough for the
    feature table's lag/rolling windows to have real (non-NaN) values.
    """
    orders = []
    today = date.today()
    for i in range(n_days):
        d = today - timedelta(days=n_days - i)
        for _ in range(per_day):
            orders.append(
                {
                    "created_at": f"{d.isoformat()}T12:00:00+00:00",
                    "total_price": 50.0,
                    "status": "completed",
                    "pickup_date": None,
                }
            )
    return orders


def test_build_daily_feature_table_covers_full_date_range_with_zero_fill():
    orders = _fake_orders(n_days=10, per_day=1)
    daily = _build_daily_feature_table(orders)
    assert len(daily) == 10
    assert daily["order_count"].sum() == 10
    assert daily["confirmed_for_date"].sum() == 0  # no pickup_date set anywhere


def test_build_daily_feature_table_fills_gap_days_with_zero():
    today = date.today()
    orders = [
        {"created_at": f"{today.isoformat()}T09:00:00+00:00", "total_price": 40.0, "status": "completed", "pickup_date": None},
        {"created_at": f"{(today - timedelta(days=5)).isoformat()}T09:00:00+00:00", "total_price": 60.0, "status": "completed", "pickup_date": None},
    ]
    daily = _build_daily_feature_table(orders)
    assert len(daily) == 6  # the 5-day gap is filled in, not skipped
    assert (daily["order_count"] == 0).sum() == 4  # every day but the two real ones


def test_build_daily_feature_table_counts_confirmed_pickups_for_open_orders_only():
    today = date.today()
    target = (today + timedelta(days=3)).isoformat()
    orders = _fake_orders(n_days=10, per_day=1)
    orders.append({"created_at": f"{today.isoformat()}T09:00:00+00:00", "total_price": 50.0, "status": "confirmed", "pickup_date": target})
    orders.append({"created_at": f"{today.isoformat()}T09:00:00+00:00", "total_price": 50.0, "status": "cancelled", "pickup_date": target})
    daily = _build_daily_feature_table(orders)
    # cancelled doesn't count; a pickup_date past the daily table's own
    # date range (built only up to the last order's created_at) is
    # simply absent from confirmed_for_date's index, not an error.
    assert daily["confirmed_for_date"].sum() == 0


def test_tomorrow_feature_row_has_all_expected_columns():
    orders = _fake_orders(n_days=35, per_day=2)
    daily = _build_daily_feature_table(orders)
    row = _tomorrow_feature_row(daily)
    assert list(row.columns) == FEATURE_COLUMNS
    assert len(row) == 1
    assert row["lag_1_count"].iloc[0] == daily["order_count"].iloc[-1]


def test_workload_level_buckets_by_zscore():
    assert _workload_level(5, [5, 5, 5, 5, 5]) == "Moderate"  # no variance -> Moderate
    assert _workload_level(1, [5, 5, 5, 5, 10]) == "Low"
    assert _workload_level(20, [5, 5, 5, 5, 10]) == "Very High"


def test_workload_level_needs_at_least_two_samples():
    assert _workload_level(100, []) == "Moderate"
    assert _workload_level(100, [5]) == "Moderate"


def test_confidence_from_trees_high_when_trees_agree():
    trees = np.array([10.0, 10.1, 9.9, 10.0, 10.0])
    confidence = _confidence_from_trees(trees, prediction=10.0, confirmed_count=0)
    assert confidence >= 85


def test_confidence_from_trees_low_when_trees_disagree():
    trees = np.array([2.0, 15.0, 4.0, 18.0, 1.0])
    confidence = _confidence_from_trees(trees, prediction=8.0, confirmed_count=0)
    assert confidence <= 60


def test_confidence_from_trees_boosted_by_confirmed_orders():
    trees = np.array([8.0, 8.0, 8.0])
    base = _confidence_from_trees(trees, prediction=8.0, confirmed_count=0)
    boosted = _confidence_from_trees(trees, prediction=8.0, confirmed_count=4)
    assert boosted > base


def test_confidence_from_trees_clamped_to_range():
    perfect_agreement = np.array([5.0, 5.0, 5.0])
    assert _confidence_from_trees(perfect_agreement, prediction=5.0, confirmed_count=20) <= 95
    wild_disagreement = np.array([0.0, 100.0, 0.0, 100.0])
    assert _confidence_from_trees(wild_disagreement, prediction=50.0, confirmed_count=0) >= 40


def test_build_reason_cites_top_features_and_confirmed_orders():
    reason = _build_reason(
        weekday_name="Saturday",
        is_weekend=True,
        confirmed_count=3,
        top_features=["recent daily order volume", "which day of the week tomorrow is"],
    )
    assert "recent daily order volume" in reason
    assert "Saturdays tend to run busier" in reason
    assert "3 orders already confirmed" in reason


def test_build_reason_omits_confirmed_clause_when_zero():
    reason = _build_reason(
        weekday_name="Tuesday", is_weekend=False, confirmed_count=0, top_features=["a", "b"]
    )
    assert "confirmed" not in reason


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
