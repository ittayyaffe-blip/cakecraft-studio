"""Dependency-free self-check for `app.api.routes.chat` -- the website
chat widget's two endpoints (/ask, /order). Run from `backend/`:

    python -m tests.test_chat_route

order_service.find_or_create_customer/find_open_order_for_customer and
inbound_service.process_chat_message/process_order_assistant_message are
mocked at their exact call boundary (same convention every other route
test module in this project uses) so the route's own real wiring runs
for real. answer_customer_question's/run_order_assistant_turn's own AI/
guardrail behavior is covered in test_agent_service.py/
test_agent_order_assistant.py; process_chat_message's/
process_order_assistant_message's own orchestration is covered in
test_inbound_service.py -- this file is purely "did the route wire the
right pieces together with the right data."
"""

from unittest.mock import patch

from app.api.routes import chat
from app.schemas.chat import ChatAskRequest, ChatOrderDraft, ChatOrderRequest

_REQUEST = ChatAskRequest(name="Jane Doe", email="jane@example.com", question="Is it gluten-free?", orderId=None)


def test_ask_finds_or_creates_the_customer_and_derives_the_order_server_side():
    with (
        patch.object(chat.order_service, "find_or_create_customer", return_value="cust-1") as mock_find_customer,
        patch.object(chat.order_service, "find_open_order_for_customer", return_value=(None, "none")) as mock_find_order,
        patch.object(
            chat.inbound_service,
            "process_chat_message",
            return_value={"answer": "Yes, it's gluten-free.", "intent": "PRODUCT_QUESTION"},
        ) as mock_process,
    ):
        response = chat.ask(_REQUEST)

    assert response == {"answer": "Yes, it's gluten-free.", "intent": "PRODUCT_QUESTION"}
    mock_find_customer.assert_called_once_with("Jane Doe", None, "jane@example.com")
    mock_find_order.assert_called_once_with("cust-1")
    mock_process.assert_called_once_with(
        "Is it gluten-free?", {"id": "cust-1", "name": "Jane Doe", "email": "jane@example.com"}, None, "none"
    )


def test_ask_surfaces_new_order_inquiry_intent_for_the_widgets_ordering_nudge():
    # ChatAskResponse.intent is what the widget uses to offer "Start an
    # order?" -- this pins that the route actually passes it through,
    # not just answer text.
    with (
        patch.object(chat.order_service, "find_or_create_customer", return_value="cust-1"),
        patch.object(chat.order_service, "find_open_order_for_customer", return_value=(None, "none")),
        patch.object(
            chat.inbound_service,
            "process_chat_message",
            return_value={"answer": "Sure, what would you like?", "intent": "NEW_ORDER_INQUIRY"},
        ),
    ):
        response = chat.ask(_REQUEST)

    assert response["intent"] == "NEW_ORDER_INQUIRY"


def test_ask_ignores_client_supplied_orderid_and_uses_the_derived_order_instead():
    # Security-relevant: request.orderId is never trusted for grounding --
    # see ChatAskRequest's own note. A customer can't point the AI at
    # someone else's order by passing an arbitrary id.
    spoofed_request = ChatAskRequest(name="Jane Doe", email="jane@example.com", question="How's my order?", orderId="someone-elses-order-id")
    real_order = {"id": "order-1", "status": "in_progress"}
    with (
        patch.object(chat.order_service, "find_or_create_customer", return_value="cust-1"),
        patch.object(chat.order_service, "find_open_order_for_customer", return_value=(real_order, "matched")) as mock_find_order,
        patch.object(chat.inbound_service, "process_chat_message", return_value={"answer": "It's in progress!"}) as mock_process,
    ):
        chat.ask(spoofed_request)

    mock_find_order.assert_called_once_with("cust-1")  # never passed the client's orderId
    assert mock_process.call_args.args[2] == real_order  # the server-derived order, not the spoofed one


def test_ask_rejects_a_blank_question_before_touching_any_service():
    blank_request = ChatAskRequest(name="Jane Doe", email="jane@example.com", question="   ", orderId=None)
    with (
        patch.object(chat.order_service, "find_or_create_customer") as mock_find_customer,
        patch.object(chat.inbound_service, "process_chat_message") as mock_process,
    ):
        try:
            chat.ask(blank_request)
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 400
        else:
            raise AssertionError("expected an HTTPException(400) for a blank question")
    mock_find_customer.assert_not_called()
    mock_process.assert_not_called()


# --- POST /order --------------------------------------------------------


def test_order_finds_or_creates_the_customer_and_hands_off_with_the_draft():
    request = ChatOrderRequest(
        name="Jane Doe", email="jane@example.com", message="Yes, please confirm",
        draft=ChatOrderDraft(templateId="tpl-1"),
    )
    with (
        patch.object(chat.order_service, "find_or_create_customer", return_value="cust-1") as mock_find_customer,
        patch.object(
            chat.inbound_service,
            "process_order_assistant_message",
            return_value={"reply": "Order created!", "draft": {}, "orderCreated": True, "orderId": "order-1"},
        ) as mock_process,
    ):
        response = chat.order(request)

    assert response == {"reply": "Order created!", "draft": {}, "orderCreated": True, "orderId": "order-1"}
    mock_find_customer.assert_called_once_with("Jane Doe", None, "jane@example.com")
    mock_process.assert_called_once_with(
        "Yes, please confirm",
        {"id": "cust-1", "name": "Jane Doe", "email": "jane@example.com"},
        {
            "templateId": "tpl-1", "cakeSizeId": None, "flavorId": None, "fillingId": None,
            "frostingId": None, "phone": None, "pickupDate": None, "pickupTime": None,
            "guestCount": None, "specialRequestNote": None, "awaitingOrderConfirmation": False,
        },
        trigger_context=None,
    )


def test_order_passes_an_empty_draft_on_the_first_turn():
    request = ChatOrderRequest(name="Jane Doe", email="jane@example.com", message="I'd like to order a cake", draft=None)
    with (
        patch.object(chat.order_service, "find_or_create_customer", return_value="cust-1"),
        patch.object(
            chat.inbound_service,
            "process_order_assistant_message",
            return_value={"reply": "What would you like?", "draft": {}, "orderCreated": False, "orderId": None},
        ) as mock_process,
    ):
        chat.order(request)

    assert mock_process.call_args.args[2] == {}


def test_order_passes_trigger_context_through_when_present():
    request = ChatOrderRequest(
        name="Jane Doe", email="jane@example.com", message="chocolate, impressive",
        draft=None, triggerContext="birthday cake for 20 nice people",
    )
    with (
        patch.object(chat.order_service, "find_or_create_customer", return_value="cust-1"),
        patch.object(
            chat.inbound_service,
            "process_order_assistant_message",
            return_value={"reply": "Got it!", "draft": {}, "orderCreated": False, "orderId": None},
        ) as mock_process,
    ):
        chat.order(request)

    assert mock_process.call_args.kwargs["trigger_context"] == "birthday cake for 20 nice people"


def test_order_rejects_a_blank_message_before_touching_any_service():
    request = ChatOrderRequest(name="Jane Doe", email="jane@example.com", message="   ", draft=None)
    with (
        patch.object(chat.order_service, "find_or_create_customer") as mock_find_customer,
        patch.object(chat.inbound_service, "process_order_assistant_message") as mock_process,
    ):
        try:
            chat.order(request)
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 400
        else:
            raise AssertionError("expected an HTTPException(400) for a blank message")
    mock_find_customer.assert_not_called()
    mock_process.assert_not_called()


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
