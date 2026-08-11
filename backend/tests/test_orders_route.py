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

from unittest.mock import patch

from app.api.routes import orders
from app.schemas.order import OrderCreateRequest

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


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
