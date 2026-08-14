"""Dependency-free self-check for payment_service.py -- the simulated/demo
payment lifecycle (see that module's own top docstring: no real provider,
no real card data, ever). Run from `backend/`:

    python -m tests.test_payment_service

simulate_payment's own orchestration (idempotency, the one automatic
pending -> confirmed transition, audit, notification) is tested against
mocked order_service/audit_service/notification_service calls and mocked
get_or_create_payment/get_payment_for_order -- the exact call boundary
each already established for their own modules (same convention as
test_agent_order_assistant.py). get_or_create_payment itself is tested
separately, directly against a mocked supabase client, to prove its own
get-or-create logic (the one-payment-row-per-order guarantee).
"""

from types import SimpleNamespace
from unittest.mock import patch

from app.services import payment_service

_ORDER = {"id": "order-1", "status": "pending", "total_price": 152.0}
_PENDING_PAYMENT = {"id": "pay-1", "order_id": "order-1", "status": "pending", "amount": 152.0}
_PAID_PAYMENT = {
    **_PENDING_PAYMENT,
    "status": "paid",
    "paid_at": "2026-08-12T10:00:00+00:00",
    "simulated_reference": "SIM-EXISTING1",
}


def _run(
    order_id="order-1",
    *,
    order=None,
    existing_payment=None,
    update_returns_row=True,
    updated_payment=None,
    race_reread_payment=None,
    confirmed_order=None,
):
    order = order if order is not None else {**_ORDER, "id": order_id}
    existing_payment = existing_payment if existing_payment is not None else {**_PENDING_PAYMENT, "order_id": order_id}
    updated_payment = updated_payment or {
        **existing_payment, "status": "paid",
        "paid_at": "2026-08-12T11:00:00+00:00", "simulated_reference": "SIM-NEWPAY001",
    }
    confirmed_order = confirmed_order if confirmed_order is not None else {**order, "status": "confirmed"}

    with (
        patch.object(payment_service.order_service, "get_order_by_id", return_value=order),
        patch.object(payment_service, "get_or_create_payment", return_value=existing_payment) as mock_get_or_create,
        patch.object(payment_service, "get_payment_for_order", return_value=race_reread_payment) as mock_reread,
        patch.object(payment_service, "supabase") as mock_supabase,
        patch.object(payment_service.order_service, "update_order_status", return_value=confirmed_order) as mock_update_status,
        patch.object(payment_service.audit_service, "record_event") as mock_record_event,
        patch.object(payment_service.notification_service, "create_notification_for_order_event") as mock_notify,
    ):
        update_chain = mock_supabase.table.return_value.update.return_value.eq.return_value.eq.return_value.execute
        update_chain.return_value = SimpleNamespace(data=[updated_payment] if update_returns_row else [])
        result = payment_service.simulate_payment(order_id)

    return result, SimpleNamespace(
        get_or_create=mock_get_or_create, reread=mock_reread, supabase=mock_supabase,
        update_status=mock_update_status, audit=mock_record_event, notify=mock_notify,
    )


# --- Authoritative amount, never client-supplied ----------------------------


def test_amount_comes_from_orders_total_price_not_any_caller_supplied_number():
    # simulate_payment's own signature takes only order_id -- there is
    # nowhere for a caller to even pass an amount (see this module's own
    # docstring). Confirmed here: whatever orders.total_price says is
    # exactly what get_or_create_payment is asked to charge (simulated).
    order = {**_ORDER, "total_price": 168.0}
    _, mocks = _run(order=order)
    mocks.get_or_create.assert_called_once_with("order-1", 168.0)


def test_paid_at_and_simulated_reference_are_populated_on_success():
    result, _ = _run()
    payment = result["payment"]
    assert payment["paid_at"]
    assert payment["simulated_reference"].startswith("SIM-")


# --- Explicit Pay Now succeeds, transitions the order -----------------------


def test_explicit_pay_now_produces_paid_and_moves_pending_to_confirmed():
    result, mocks = _run()
    assert result["payment"]["status"] == "paid"
    assert result["order_status"] == "confirmed"
    mocks.update_status.assert_called_once_with("order-1", "confirmed")
    mocks.audit.assert_called_once()
    assert mocks.audit.call_args.kwargs["actor_id"] is None  # system-initiated, no staff member
    mocks.notify.assert_called_once_with({**_ORDER, "status": "confirmed"}, "confirmed")


def test_payment_does_not_move_an_already_confirmed_order_to_in_progress():
    # If an order is already past "pending" for any reason, a (first) paid
    # transition must never advance it further -- only pending -> confirmed
    # is automatic; in_progress/ready/completed stay staff-driven.
    order = {**_ORDER, "status": "confirmed"}
    result, mocks = _run(order=order)
    assert result["order_status"] == "confirmed"
    mocks.update_status.assert_not_called()
    mocks.notify.assert_not_called()


# --- Idempotency: retries/double-clicks never double-charge or duplicate ---


def test_repeated_payment_is_idempotent_no_second_transition():
    result, mocks = _run(existing_payment=_PAID_PAYMENT)
    assert result["payment"] == _PAID_PAYMENT
    assert result["order_status"] == "pending"  # unchanged -- this call never touched the order
    mocks.supabase.table.return_value.update.assert_not_called()
    mocks.update_status.assert_not_called()


def test_duplicate_payment_does_not_create_a_duplicate_confirmation_notification():
    _, mocks = _run(existing_payment=_PAID_PAYMENT)
    mocks.notify.assert_not_called()


def test_concurrent_call_that_loses_the_conditional_update_race_rereads_consistently():
    # Two near-simultaneous calls for the same order: this one's UPDATE
    # ... WHERE status='pending' matched zero rows because the other
    # request already flipped it -- re-read, don't fail or retry the
    # transition a second time. get_order_by_id is called twice in this
    # path (the initial load, then the race-loss re-read) -- side_effect
    # models the second call seeing the winner's already-applied update.
    confirmed_order = {**_ORDER, "status": "confirmed"}
    with (
        patch.object(payment_service.order_service, "get_order_by_id", side_effect=[_ORDER, confirmed_order]),
        patch.object(payment_service, "get_or_create_payment", return_value=_PENDING_PAYMENT),
        patch.object(payment_service, "get_payment_for_order", return_value=_PAID_PAYMENT) as mock_reread,
        patch.object(payment_service, "supabase") as mock_supabase,
        patch.object(payment_service.order_service, "update_order_status") as mock_update_status,
        patch.object(payment_service.notification_service, "create_notification_for_order_event") as mock_notify,
    ):
        mock_supabase.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = (
            SimpleNamespace(data=[])  # lost the race -- zero rows matched
        )
        result = payment_service.simulate_payment("order-1")

    assert result["payment"] == _PAID_PAYMENT
    assert result["order_status"] == "confirmed"  # reflects the winner's already-applied update
    mock_update_status.assert_not_called()  # this call never performed the transition itself
    mock_notify.assert_not_called()  # nor drafted a second notification
    mock_reread.assert_called_once_with("order-1")


# --- Rejections --------------------------------------------------------------


def test_cancelled_order_cannot_be_paid():
    with patch.object(payment_service.order_service, "get_order_by_id", return_value={**_ORDER, "status": "cancelled"}):
        try:
            payment_service.simulate_payment("order-1")
        except payment_service.OrderNotPayableError:
            pass
        else:
            raise AssertionError("expected OrderNotPayableError for a cancelled order")


def test_nonexistent_order_raises_order_not_found():
    with patch.object(payment_service.order_service, "get_order_by_id", return_value=None):
        try:
            payment_service.simulate_payment("does-not-exist")
        except payment_service.OrderNotFoundError:
            pass
        else:
            raise AssertionError("expected OrderNotFoundError for a missing order")


# --- get_or_create_payment: exactly one payment row per order --------------


def test_get_or_create_payment_creates_a_pending_row_when_none_exists_yet():
    with patch.object(payment_service, "supabase") as mock_supabase:
        mock_supabase.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
            SimpleNamespace(data=None)
        )
        mock_supabase.table.return_value.insert.return_value.execute.return_value = SimpleNamespace(
            data=[{"id": "pay-1", "order_id": "order-1", "status": "pending", "amount": 152.0}]
        )
        payment = payment_service.get_or_create_payment("order-1", 152.0)

    assert payment["status"] == "pending"
    assert payment["amount"] == 152.0
    mock_supabase.table.return_value.insert.assert_called_once_with(
        {"order_id": "order-1", "status": "pending", "amount": 152.0}
    )


def test_get_or_create_payment_reuses_the_one_existing_row_never_a_second():
    existing = {"id": "pay-1", "order_id": "order-1", "status": "pending", "amount": 152.0}
    with patch.object(payment_service, "supabase") as mock_supabase:
        mock_supabase.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
            SimpleNamespace(data=existing)
        )
        payment = payment_service.get_or_create_payment("order-1", 152.0)

    assert payment == existing
    mock_supabase.table.return_value.insert.assert_not_called()  # unique(order_id) -- never a second row


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
