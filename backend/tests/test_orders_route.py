"""Dependency-free self-check for `app.api.routes.orders` -- Step 5's
"order received" notification hook, plus the order-form Notes field's
"process_order_note" hook (see inbound_service.py). Run from `backend/`:

    python -m tests.test_orders_route

create_order/order_service.get_order_by_id/notification_service.
create_notification_for_order_event/inbound_service.process_order_note
are mocked at their exact call boundary (same convention every other test
module in this project uses) so the route's own real orchestration logic
runs for real.
"""

import uuid
from unittest.mock import patch

from fastapi import BackgroundTasks

from app.api.routes import orders
from app.schemas.order import OrderCreateRequest
from app.services import payment_service

_REQUEST = OrderCreateRequest(
    template_id="template-1",
    cake_size_id="size-1",
    flavor_id="flavor-1",
    filling_id="filling-1",
    frosting_id="frosting-1",
    customer_name="Jane Doe",
    customer_phone="+33 6 12 34 56 78",
    customer_email="jane@example.com",
    notes=None,
)

_JOINED_ORDER = {
    "id": "order-1",
    "customer_id": "cust-1",
    "status": "pending",
    "notes": None,
    "customers": {"id": "cust-1", "name": "Jane Doe", "email": "jane@example.com"},
    "cake_templates": {"name": "Ivory Three-Tier Classic"},
}

_JOINED_ORDER_WITH_NOTES = {**_JOINED_ORDER, "id": "order-2", "notes": "Is it a kosher cake?"}


def test_create_order_route_drafts_an_order_received_notification():
    with (
        patch.object(orders, "create_order", return_value="order-1") as mock_create_order,
        patch.object(orders.order_service, "get_order_by_id", return_value=_JOINED_ORDER) as mock_get_order,
        patch.object(orders.notification_service, "create_notification_for_order_event") as mock_create_notif,
        patch.object(orders.inbound_service, "process_order_note") as mock_process_note,
    ):
        response = orders.create_order_route(_REQUEST)

    assert response == {"orderId": "order-1"}
    mock_create_order.assert_called_once_with(_REQUEST.model_dump())
    mock_get_order.assert_called_once_with("order-1")
    # The correct, freshly-fetched (joined) order and the "pending" status
    # -- never the raw request payload, never a guessed status.
    mock_create_notif.assert_called_once_with(_JOINED_ORDER, "pending")
    # Still called even with blank notes -- process_order_note itself is
    # responsible for the blank-notes no-op (see test_inbound_service.py).
    mock_process_note.assert_called_once_with(_JOINED_ORDER, _JOINED_ORDER["customers"])


def test_create_order_route_still_returns_order_id_when_notification_drafting_fails():
    # Mirrors admin/orders.py's status-update route: a failure in the
    # notification step must never fail order creation itself -- the
    # customer's order still exists even if the draft-a-notification step
    # had a bad moment.
    with (
        patch.object(orders, "create_order", return_value="order-1"),
        patch.object(orders.order_service, "get_order_by_id", side_effect=RuntimeError("db hiccup")),
        patch.object(orders.notification_service, "create_notification_for_order_event") as mock_create_notif,
        patch.object(orders.inbound_service, "process_order_note") as mock_process_note,
    ):
        response = orders.create_order_route(_REQUEST)

    assert response == {"orderId": "order-1"}
    mock_create_notif.assert_not_called()
    # created_order is None (get_order_by_id raised) -- nothing to process.
    mock_process_note.assert_not_called()


def test_create_order_route_processes_a_non_blank_note_via_the_existing_inbound_pipeline():
    with (
        patch.object(orders, "create_order", return_value="order-2"),
        patch.object(orders.order_service, "get_order_by_id", return_value=_JOINED_ORDER_WITH_NOTES),
        patch.object(orders.notification_service, "create_notification_for_order_event"),
        patch.object(orders.inbound_service, "process_order_note") as mock_process_note,
    ):
        response = orders.create_order_route(_REQUEST)

    assert response == {"orderId": "order-2"}
    mock_process_note.assert_called_once_with(_JOINED_ORDER_WITH_NOTES, _JOINED_ORDER_WITH_NOTES["customers"])


def test_create_order_route_still_returns_order_id_when_note_processing_fails():
    # Same fail-open guarantee as the notification hook: a bad moment in
    # the inbound/AI pipeline must never fail order creation itself.
    with (
        patch.object(orders, "create_order", return_value="order-2"),
        patch.object(orders.order_service, "get_order_by_id", return_value=_JOINED_ORDER_WITH_NOTES),
        patch.object(orders.notification_service, "create_notification_for_order_event"),
        patch.object(orders.inbound_service, "process_order_note", side_effect=RuntimeError("Anthropic is down")),
    ):
        response = orders.create_order_route(_REQUEST)

    assert response == {"orderId": "order-2"}


def test_create_order_route_returns_404_when_template_not_found():
    with patch.object(orders, "create_order", return_value=None):
        try:
            orders.create_order_route(_REQUEST)
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 404
        else:
            raise AssertionError("expected an HTTPException(404) when create_order returns None")


# --- GET /orders/{id} -- minimal public order view (payment.html) ----------

_UUID = uuid.UUID("11111111-1111-1111-1111-111111111111")

_ORDER_FOR_PUBLIC_VIEW = {
    "id": str(_UUID),
    "status": "pending",
    "total_price": 152.0,
    "configuration": {"cakeSize": {"name": "Large"}, "flavor": {"name": "Chocolate"}},
    "cake_templates": {"name": "Chocolate Confetti Celebration"},
}


def test_get_order_route_returns_public_view_with_pending_payment():
    with (
        patch.object(orders.order_service, "get_order_by_id", return_value=_ORDER_FOR_PUBLIC_VIEW),
        patch.object(orders.payment_service, "get_payment_for_order", return_value=None),
    ):
        result = orders.get_order_route(_UUID)

    assert result == {
        "orderId": str(_UUID),
        "templateName": "Chocolate Confetti Celebration",
        "configuration": _ORDER_FOR_PUBLIC_VIEW["configuration"],
        "totalPrice": 152.0,
        "orderStatus": "pending",
        "paymentStatus": "pending",  # no payment row yet -- defaults to pending, never invented as "paid"
    }


def test_get_order_route_returns_public_view_with_paid_payment():
    payment = {"status": "paid", "amount": 152.0, "simulated_reference": "SIM-ABC123"}
    with (
        patch.object(orders.order_service, "get_order_by_id", return_value={**_ORDER_FOR_PUBLIC_VIEW, "status": "confirmed"}),
        patch.object(orders.payment_service, "get_payment_for_order", return_value=payment),
    ):
        result = orders.get_order_route(_UUID)

    assert result["orderStatus"] == "confirmed"
    assert result["paymentStatus"] == "paid"


def test_get_order_route_returns_404_for_missing_order():
    with patch.object(orders.order_service, "get_order_by_id", return_value=None):
        try:
            orders.get_order_route(_UUID)
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 404
        else:
            raise AssertionError("expected an HTTPException(404) for a missing order")


# --- POST /orders/{id}/pay ---------------------------------------------------


def test_pay_order_route_returns_payment_and_order_status():
    # The route function's own signature takes ONLY order_id (see
    # app/api/routes/orders.py) -- there is nowhere for a client to pass
    # an amount even if it tried; payment_service.simulate_payment is the
    # one and only source of the charged (simulated) amount.
    with patch.object(
        orders.payment_service,
        "simulate_payment",
        return_value={
            "payment": {"status": "paid", "amount": 152.0, "simulated_reference": "SIM-ABC123", "paid_at": "2026-08-12T10:00:00+00:00"},
            "order_status": "confirmed",
            "notification_order": None,
        },
    ) as mock_simulate:
        result = orders.pay_order_route(_UUID, BackgroundTasks())

    mock_simulate.assert_called_once_with(str(_UUID))
    assert result == {
        "paymentStatus": "paid",
        "orderStatus": "confirmed",
        "amount": 152.0,
        "simulatedReference": "SIM-ABC123",
        "paidAt": "2026-08-12T10:00:00+00:00",
    }


def test_pay_order_route_schedules_the_notification_draft_as_a_background_task():
    # Not on the critical path -- the customer-facing response must not
    # wait on drafting the confirmed-order notification (see payment_
    # service.simulate_payment's own docstring). Scheduled only when
    # simulate_payment signals a real transition just happened.
    notification_order = {"id": "order-1", "status": "confirmed"}
    background_tasks = BackgroundTasks()
    with (
        patch.object(
            orders.payment_service,
            "simulate_payment",
            return_value={
                "payment": {"status": "paid", "amount": 152.0, "simulated_reference": "SIM-ABC123", "paid_at": "t"},
                "order_status": "confirmed",
                "notification_order": notification_order,
            },
        ),
        patch.object(orders.notification_service, "create_notification_for_order_event") as mock_notify,
    ):
        orders.pay_order_route(_UUID, background_tasks)

    mock_notify.assert_not_called()  # not yet -- only scheduled, not run inline
    assert len(background_tasks.tasks) == 1
    task = background_tasks.tasks[0]
    assert task.func is mock_notify
    assert task.args == (notification_order, "confirmed")


def test_pay_order_route_schedules_no_background_task_for_an_idempotent_repeat():
    background_tasks = BackgroundTasks()
    with patch.object(
        orders.payment_service,
        "simulate_payment",
        return_value={
            "payment": {"status": "paid", "amount": 152.0, "simulated_reference": "SIM-ABC123", "paid_at": "t"},
            "order_status": "confirmed",
            "notification_order": None,  # already paid before this call -- no new transition
        },
    ):
        orders.pay_order_route(_UUID, background_tasks)

    assert len(background_tasks.tasks) == 0


def test_pay_order_route_returns_404_for_a_nonexistent_order():
    with patch.object(orders.payment_service, "simulate_payment", side_effect=payment_service.OrderNotFoundError(str(_UUID))):
        try:
            orders.pay_order_route(_UUID, BackgroundTasks())
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 404
        else:
            raise AssertionError("expected an HTTPException(404) for a nonexistent order")


def test_pay_order_route_returns_400_for_a_cancelled_order():
    with patch.object(
        orders.payment_service, "simulate_payment", side_effect=payment_service.OrderNotPayableError("cancelled")
    ):
        try:
            orders.pay_order_route(_UUID, BackgroundTasks())
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 400
        else:
            raise AssertionError("expected an HTTPException(400) for a cancelled order")


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
