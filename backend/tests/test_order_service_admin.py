"""Dependency-free self-check for the pure logic added to
`app.services.order_service` for admin order management — no network/DB
required. Run from `backend/`:

    python -m tests.test_order_service_admin

Covers pagination math and status validation only. The functions that
actually call Supabase (`list_orders`, `get_order_by_id`,
`update_order_status`) are exercised live via `fastapi.testclient.TestClient`
against the real deployment instead — see docs/EPIC1_BACKOFFICE.md.
"""

from app.services.order_service import ORDER_STATUSES, _page_to_range, update_order_status


def test_page_to_range_first_page():
    assert _page_to_range(page=1, page_size=20) == (0, 19)


def test_page_to_range_second_page():
    assert _page_to_range(page=2, page_size=20) == (20, 39)


def test_page_to_range_custom_size():
    assert _page_to_range(page=3, page_size=10) == (20, 29)


def test_order_statuses_match_db_check_constraint():
    # supabase/migrations/20260729120000_initial_schema.sql
    assert ORDER_STATUSES == (
        "pending",
        "confirmed",
        "in_progress",
        "ready",
        "completed",
        "cancelled",
    )


def test_update_order_status_rejects_invalid_status():
    try:
        update_order_status(order_id="irrelevant", new_status="not-a-real-status")
    except ValueError as exc:
        assert "not-a-real-status" in str(exc)
    else:
        raise AssertionError("expected ValueError, none was raised")


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
