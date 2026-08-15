"""Dependency-free self-check for app.services.priority_service -- pure
Python, no network/DB/Anthropic call anywhere (there is nothing to mock:
compute_priority() takes a plain dict and returns a plain dict). Run from
`backend/`:

    python -m tests.test_priority_service
"""

from datetime import datetime, timedelta, timezone

from app.services.priority_service import compute_priority

_TODAY = datetime.now(timezone.utc).date()


def _order(status, days_from_today=None, category="Birthday", pickup_date="__unset__"):
    if pickup_date == "__unset__":
        pickup_date = (_TODAY + timedelta(days=days_from_today)).isoformat() if days_from_today is not None else None
    return {
        "id": "order-1", "status": status, "pickup_date": pickup_date,
        "cake_templates": {"category": category},
    }


def test_overdue_pickup_is_critical():
    result = compute_priority(_order("confirmed", days_from_today=-3))
    assert result["priority"] == "CRITICAL"
    assert result["manager_attention"] is True
    assert "overdue" in result["reason"].lower()


def test_pickup_today_is_critical():
    result = compute_priority(_order("in_progress", days_from_today=0))
    assert result["priority"] == "CRITICAL"
    assert result["manager_attention"] is True
    assert "today" in result["reason"].lower()


def test_pickup_tomorrow_is_high():
    result = compute_priority(_order("confirmed", days_from_today=1))
    assert result["priority"] == "HIGH"
    assert result["manager_attention"] is False


def test_pickup_in_two_days_is_high():
    result = compute_priority(_order("confirmed", days_from_today=2))
    assert result["priority"] == "HIGH"


def test_pickup_in_three_days_is_not_high():
    # Boundary check: the window is <= 2 days, not < 2.
    result = compute_priority(_order("confirmed", days_from_today=3, category="Birthday"))
    assert result["priority"] == "NORMAL"


def test_confirmed_wedding_far_out_is_high():
    result = compute_priority(_order("confirmed", days_from_today=30, category="Wedding"))
    assert result["priority"] == "HIGH"
    assert result["manager_attention"] is False
    assert "wedding" in result["reason"].lower()


def test_in_progress_wedding_far_out_is_not_boosted():
    # Approved policy narrows the Wedding boost to CONFIRMED orders only
    # (production not yet started) -- an in_progress wedding far from
    # pickup doesn't get the same automatic HIGH bump.
    result = compute_priority(_order("in_progress", days_from_today=30, category="Wedding"))
    assert result["priority"] == "NORMAL"


def test_future_normal_order():
    result = compute_priority(_order("confirmed", days_from_today=10, category="Birthday"))
    assert result["priority"] == "NORMAL"
    assert result["manager_attention"] is False


def test_ready_order_with_comfortable_buffer_is_low():
    result = compute_priority(_order("ready", days_from_today=10))
    assert result["priority"] == "LOW"
    assert result["manager_attention"] is False


def test_ready_order_due_today_is_still_critical_not_low():
    # LOW is specifically "sufficient buffer" -- a ready order due today
    # still needs the same urgent attention as any other status.
    result = compute_priority(_order("ready", days_from_today=0))
    assert result["priority"] == "CRITICAL"


def test_missing_pickup_date_is_needs_info_not_critical():
    # The one explicit policy change from the original audit: missing
    # information is an EXCEPTION, never guessed into a priority level.
    for status in ("confirmed", "in_progress", "ready"):
        result = compute_priority(_order(status, pickup_date=None))
        assert result["priority"] is None
        assert result["manager_attention"] is True
        assert result["reason"] == "Pickup date missing — priority cannot be determined."


def test_pending_order_is_out_of_scope_not_flagged():
    # pending = not yet reviewed/confirmed -- nothing to prioritize for
    # production yet, and NOT the same thing as "missing information".
    result = compute_priority(_order("pending", pickup_date=None))
    assert result["priority"] is None
    assert result["manager_attention"] is False


def test_completed_and_cancelled_orders_are_out_of_scope():
    for status in ("completed", "cancelled"):
        result = compute_priority(_order(status, days_from_today=-5))
        assert result["priority"] is None
        assert result["manager_attention"] is False


def test_unparseable_pickup_date_does_not_crash():
    result = compute_priority(_order("confirmed", pickup_date="not-a-date"))
    assert result["priority"] is None
    assert result["manager_attention"] is True


def test_missing_cake_templates_relation_does_not_crash():
    order = {"id": "order-1", "status": "confirmed", "pickup_date": (_TODAY + timedelta(days=30)).isoformat()}
    result = compute_priority(order)
    assert result["priority"] == "NORMAL"  # no category available -> no Wedding boost, falls through safely


def test_deterministic_repeatability():
    order = _order("confirmed", days_from_today=1)
    first = compute_priority(order)
    second = compute_priority(order)
    third = compute_priority(dict(order))  # a fresh dict with the same facts
    assert first == second == third


def test_result_never_includes_a_safe_to_execute_or_authorization_field():
    # Priority is read-only decision support -- structurally, the return
    # shape has no field that could be mistaken for an authorization
    # signal (mirrors the same discipline bakery_manager_service's
    # safeToExecute classification already applies).
    result = compute_priority(_order("confirmed", days_from_today=0))
    assert set(result.keys()) == {"priority", "reason", "manager_attention"}


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
