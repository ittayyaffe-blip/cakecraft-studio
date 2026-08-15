"""Dependency-free self-check for order_service.create_order()'s own
id-validation/pricing/payload-building logic -- no network/DB required.
Run from `backend/`:

    python -m tests.test_order_service

order_service.get_template_by_id/get_designer_options/find_or_create_customer
and order_service.supabase are mocked at their exact call boundary (same
convention test_order_service_admin.py already established for this
module) so create_order's real validation logic runs for real. This is
the one authoritative choke point Website/Chat/WhatsApp/direct API calls
all go through -- see that function's own docstring.
"""

from types import SimpleNamespace
from unittest.mock import patch

from app.services import order_service

_TEMPLATE = {"id": "tpl-1", "name": "Classic Vanilla", "base_price": 45.0, "active": True}
_INACTIVE_TEMPLATE = {**_TEMPLATE, "id": "tpl-2", "active": False}

_OPTIONS = {
    "cake_sizes": [{"id": "size-1", "name": "Small", "price_adjustment": 0}],
    "flavors": [{"id": "flav-1", "name": "Chocolate"}],
    "fillings": [{"id": "fill-1", "name": "Chocolate Ganache"}],
    "frostings": [{"id": "frost-1", "name": "Buttercream"}],
}

_ORDER = {
    "template_id": "tpl-1",
    "cake_size_id": "size-1",
    "flavor_id": "flav-1",
    "filling_id": "fill-1",
    "frosting_id": "frost-1",
    "customer_name": "Jane Doe",
    "customer_phone": "+15551234567",
    "customer_email": "jane@example.com",
    "notes": None,
}


def _create(order=_ORDER, *, template=_TEMPLATE, options=_OPTIONS):
    """Shared harness: patches every external boundary create_order()
    itself calls, returns (order_id, mock_supabase) for assertions --
    same shape as test_agent_order_assistant.py's own _run harness.
    """
    with (
        patch.object(order_service, "get_template_by_id", return_value=template),
        patch.object(order_service, "get_designer_options", return_value=options),
        patch.object(order_service, "find_or_create_customer", return_value="cust-1"),
        patch.object(order_service, "supabase") as mock_supabase,
    ):
        mock_supabase.table.return_value.insert.return_value.execute.return_value = SimpleNamespace(
            data=[{"id": "order-1"}]
        )
        order_id = order_service.create_order(order)
    return order_id, mock_supabase


# --- Catalog validation: only a fully-active, real combination works -------


def test_valid_active_combination_creates_an_order():
    order_id, mock_supabase = _create()
    assert order_id == "order-1"
    payload = mock_supabase.table.return_value.insert.call_args.args[0]
    assert payload["status"] == "pending"
    assert payload["total_price"] == 45.0  # base_price(45) + Small's 0 adjustment -- deterministic, not guessed


def test_inactive_template_cannot_be_ordered():
    order_id, mock_supabase = _create(template=_INACTIVE_TEMPLATE)
    assert order_id is None
    mock_supabase.table.return_value.insert.assert_not_called()


def test_nonexistent_template_cannot_be_ordered():
    order_id, mock_supabase = _create(template=None)
    assert order_id is None
    mock_supabase.table.return_value.insert.assert_not_called()


def _assert_rejected(options):
    try:
        _create(options=options)
    except ValueError as exc:
        assert "Invalid" in str(exc)
    else:
        raise AssertionError("expected ValueError for an inactive/nonexistent option")


def test_inactive_size_cannot_be_ordered():
    # get_designer_options() only ever returns active=True rows for real
    # (see designer_service.py's own docstring) -- an inactive/nonexistent
    # size id simply isn't found in this list, exactly like this.
    _assert_rejected({**_OPTIONS, "cake_sizes": []})


def test_inactive_flavor_cannot_be_ordered():
    _assert_rejected({**_OPTIONS, "flavors": []})


def test_inactive_filling_cannot_be_ordered():
    _assert_rejected({**_OPTIONS, "fillings": []})


def test_inactive_frosting_cannot_be_ordered():
    _assert_rejected({**_OPTIONS, "frostings": []})


# --- Pickup scheduling (Pickup Date + Order Priority, Phase 2) -------------

from datetime import date, datetime, time, timedelta, timezone  # noqa: E402

_NOW = datetime.now(timezone.utc)


def _next_weekday(target_weekday: int, *, at_least_days_out: int = 1) -> date:
    """First date >= today + at_least_days_out that falls on the given
    weekday (Monday=0) -- avoids a hardcoded date that would go stale.
    """
    candidate = _NOW.date() + timedelta(days=at_least_days_out)
    while candidate.weekday() != target_weekday:
        candidate += timedelta(days=1)
    return candidate


def test_past_pickup_datetime_is_rejected():
    yesterday = (_NOW - timedelta(days=1)).date()
    error = order_service.validate_pickup_datetime(yesterday, time(12, 0))
    assert error is not None
    assert "past" in error.lower()


def test_monday_pickup_is_rejected():
    monday = _next_weekday(0, at_least_days_out=7)  # 0 = Monday
    error = order_service.validate_pickup_datetime(monday, time(12, 0))
    assert error is not None
    assert "monday" in error.lower()


def test_pickup_time_before_opening_is_rejected():
    tuesday = _next_weekday(1, at_least_days_out=7)
    error = order_service.validate_pickup_datetime(tuesday, time(8, 59))
    assert error is not None


def test_pickup_time_after_closing_is_rejected():
    tuesday = _next_weekday(1, at_least_days_out=7)
    error = order_service.validate_pickup_datetime(tuesday, time(18, 1))
    assert error is not None


def test_pickup_time_at_open_and_close_boundaries_is_accepted():
    tuesday = _next_weekday(1, at_least_days_out=7)
    assert order_service.validate_pickup_datetime(tuesday, time(9, 0)) is None
    assert order_service.validate_pickup_datetime(tuesday, time(18, 0)) is None


def test_valid_future_non_monday_pickup_is_accepted():
    tuesday = _next_weekday(1, at_least_days_out=30)
    assert order_service.validate_pickup_datetime(tuesday, time(12, 0)) is None


def test_rush_warning_appended_when_inside_category_minimum_lead_time():
    soon = _NOW.date() + timedelta(days=1)  # 1 day out -- inside every collection's minimum
    with patch.object(order_service, "get_template_by_id", return_value={"category": "Wedding"}):
        result = order_service.annotate_notes_with_rush_warning("tpl-1", "Please make it blue.", soon)
    assert "Please make it blue." in result
    assert "rush" in result.lower()
    assert "wedding" in result.lower()


def test_no_rush_warning_when_outside_category_minimum_lead_time():
    far_out = _NOW.date() + timedelta(days=60)
    with patch.object(order_service, "get_template_by_id", return_value={"category": "Wedding"}):
        result = order_service.annotate_notes_with_rush_warning("tpl-1", "Please make it blue.", far_out)
    assert result == "Please make it blue."


def test_rush_warning_with_no_existing_notes_returns_just_the_warning():
    soon = _NOW.date() + timedelta(days=1)
    with patch.object(order_service, "get_template_by_id", return_value={"category": "Corporate"}):
        result = order_service.annotate_notes_with_rush_warning("tpl-1", None, soon)
    assert result is not None
    assert "rush" in result.lower()


def test_rush_warning_gracefully_skipped_for_unknown_template():
    soon = _NOW.date() + timedelta(days=1)
    with patch.object(order_service, "get_template_by_id", return_value=None):
        result = order_service.annotate_notes_with_rush_warning("tpl-missing", "Notes.", soon)
    assert result == "Notes."


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
