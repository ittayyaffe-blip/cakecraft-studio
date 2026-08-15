"""Dependency-free self-check for the pure logic added to
`app.services.order_service` for admin order management — no network/DB
required. Run from `backend/`:

    python -m tests.test_order_service_admin

Covers pagination math and status validation only. The functions that
actually call Supabase (`list_orders`, `get_order_by_id`,
`update_order_status`) are exercised live via `fastapi.testclient.TestClient`
against the real deployment instead — see docs/EPIC1_BACKOFFICE.md.
"""

from types import SimpleNamespace
from unittest.mock import patch

from app.services import order_service
from app.services.order_service import ORDER_STATUSES, _page_to_range, find_open_order_for_customer, update_order_status


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


# --- Production-path transition validation (Order Stage workflow) ----------
# pending -> confirmed is normally automatic, via payment_service.
# simulate_payment (which never calls this function -- see its own
# docstring), so this validation never affects that path; it governs the
# admin-driven staff workflow only.


def _mock_update_and_refetch(mock_supabase, updated_order):
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[updated_order]
    )
    mock_supabase.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
        SimpleNamespace(data=updated_order)
    )


def test_update_order_status_allows_the_normal_production_path():
    steps = [("pending", "confirmed"), ("confirmed", "in_progress"), ("in_progress", "ready"), ("ready", "completed")]
    for current, new in steps:
        with patch.object(order_service, "supabase") as mock_supabase:
            _mock_update_and_refetch(mock_supabase, {"id": "order-1", "status": new})
            result = update_order_status("order-1", new, current_status=current)
        assert result["status"] == new, f"{current} -> {new} should be allowed"


def test_update_order_status_allows_cancel_from_any_non_terminal_status():
    for current in ("pending", "confirmed", "in_progress", "ready"):
        with patch.object(order_service, "supabase") as mock_supabase:
            _mock_update_and_refetch(mock_supabase, {"id": "order-1", "status": "cancelled"})
            result = update_order_status("order-1", "cancelled", current_status=current)
        assert result["status"] == "cancelled", f"cancel from {current} should be allowed"


def test_update_order_status_allows_resaving_the_same_status_as_a_no_op():
    # The admin drawer's status dropdown defaults to the order's current
    # status -- clicking Update Status without changing it must not error.
    with patch.object(order_service, "supabase") as mock_supabase:
        _mock_update_and_refetch(mock_supabase, {"id": "order-1", "status": "confirmed"})
        result = update_order_status("order-1", "confirmed", current_status="confirmed")
    assert result["status"] == "confirmed"


def test_update_order_status_rejects_skipping_a_production_stage():
    jumps = [
        ("pending", "in_progress"), ("pending", "ready"), ("pending", "completed"),
        ("confirmed", "ready"), ("confirmed", "completed"), ("in_progress", "completed"),
    ]
    for current, new in jumps:
        try:
            update_order_status("order-1", new, current_status=current)
        except ValueError as exc:
            assert current in str(exc) and new in str(exc)
        else:
            raise AssertionError(f"expected ValueError for {current} -> {new}")


def test_update_order_status_rejects_moving_backward():
    for current, new in [("in_progress", "confirmed"), ("ready", "in_progress"), ("completed", "ready")]:
        try:
            update_order_status("order-1", new, current_status=current)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for {current} -> {new}")


def test_update_order_status_rejects_any_transition_out_of_a_terminal_status():
    for current in ("completed", "cancelled"):
        for new in ORDER_STATUSES:
            if new == current:
                continue
            try:
                update_order_status("order-1", new, current_status=current)
            except ValueError:
                pass
            else:
                raise AssertionError(f"expected ValueError for {current} -> {new}")


# --- find_open_order_for_customer (Step 3) ----------------------------
# get_orders_for_customer is mocked directly (function-level, not
# supabase-level) -- find_open_order_for_customer's own real filtering
# logic runs against fixed order lists.


def test_find_open_order_for_customer_one_open_order_is_a_confident_match():
    orders = [{"id": "order-1", "status": "in_progress"}, {"id": "order-2", "status": "completed"}]
    with patch.object(order_service, "get_orders_for_customer", return_value=orders):
        order, status = find_open_order_for_customer("cust-1")
    assert order == orders[0]
    assert status == "matched"


def test_find_open_order_for_customer_no_open_orders():
    orders = [{"id": "order-1", "status": "completed"}, {"id": "order-2", "status": "cancelled"}]
    with patch.object(order_service, "get_orders_for_customer", return_value=orders):
        order, status = find_open_order_for_customer("cust-1")
    assert order is None
    assert status == "none"


def test_find_open_order_for_customer_no_orders_at_all():
    with patch.object(order_service, "get_orders_for_customer", return_value=[]):
        order, status = find_open_order_for_customer("cust-1")
    assert order is None
    assert status == "none"


def test_find_or_create_customer_reuses_an_existing_row_by_email():
    from types import SimpleNamespace

    with patch.object(order_service, "supabase") as mock_supabase:
        mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(
            data=[{"id": "cust-existing"}]
        )
        customer_id = order_service.find_or_create_customer("Jane Doe", None, "jane@example.com")

    assert customer_id == "cust-existing"
    mock_supabase.table.return_value.insert.assert_not_called()


def test_find_or_create_customer_creates_a_new_row_when_none_matches():
    from types import SimpleNamespace

    with patch.object(order_service, "supabase") as mock_supabase:
        mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(
            data=[]
        )
        mock_supabase.table.return_value.insert.return_value.execute.return_value = SimpleNamespace(
            data=[{"id": "cust-new"}]
        )
        customer_id = order_service.find_or_create_customer("New Customer", None, "new@example.com")

    assert customer_id == "cust-new"
    inserted_payload = mock_supabase.table.return_value.insert.call_args.args[0]
    # No phone required (the chat widget's lightweight identity capture
    # never collects one) -- customers.phone is nullable for exactly this.
    assert inserted_payload == {"name": "New Customer", "phone": None, "email": "new@example.com"}


def test_find_open_order_for_customer_multiple_open_orders_is_ambiguous():
    orders = [
        {"id": "order-1", "status": "confirmed"},
        {"id": "order-2", "status": "in_progress"},
    ]
    with patch.object(order_service, "get_orders_for_customer", return_value=orders):
        order, status = find_open_order_for_customer("cust-1")
    # Must not arbitrarily pick one -- the AI must not accidentally answer
    # about the wrong cake.
    assert order is None
    assert status == "ambiguous"


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
