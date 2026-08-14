"""Dependency-free self-check for agent_service.run_order_assistant_turn
-- the chat-assisted ordering MVP. Run from `backend/`:

    python -m tests.test_agent_order_assistant

Same mocking boundary as test_agent_service.py's answer_customer_question
tests: rag_service isn't involved here at all (this prompt doesn't use
RAG), but template_service/designer_service (the catalog),
agent_service.anthropic (Claude), agent_service.supabase (for
_insert_chat_answer's insert), and order_service/notification_service
are all mocked at their exact call boundary -- the real prompt-building,
id-validation, and confirmation-gating logic inside
run_order_assistant_turn runs for real against fixed inputs.
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

from app.services import agent_service

_CUSTOMER = {"id": "cust-1", "name": "Jane Doe", "email": "jane@example.com"}

_TEMPLATES = [{"id": "tpl-1", "name": "Classic Vanilla", "category": "Birthday"}]
_OPTIONS = {
    "cake_sizes": [{"id": "size-1", "name": "Medium (serves 12)"}],
    "flavors": [{"id": "flav-1", "name": "Chocolate"}],
    "fillings": [{"id": "fill-1", "name": "Buttercream"}],
    "frostings": [{"id": "frost-1", "name": "Vanilla Buttercream"}],
}

_COMPLETE_DRAFT = {
    "templateId": "tpl-1",
    "cakeSizeId": "size-1",
    "flavorId": "flav-1",
    "fillingId": "fill-1",
    "frostingId": "frost-1",
    "phone": "+15551234567",
}


def _fake_claude_response(**fields):
    payload = {
        "templateId": None, "cakeSizeId": None, "flavorId": None, "fillingId": None,
        "frostingId": None, "phone": None, "confirmedNow": False, "reply": "Sure, what would you like?",
    }
    payload.update(fields)
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(payload))])


def _mock_insert_result(notif_id="notif-order-1"):
    return SimpleNamespace(data=[{"id": notif_id, "status": "sent", "channel": "chat"}])


def _run(message, draft, claude_fields, *, create_order_side_effect=None):
    """Shared harness: patches every external boundary, returns
    run_order_assistant_turn's result plus the mocks for assertions.
    """
    with (
        patch.object(agent_service.settings, "anthropic_api_key", "fake-key-for-test"),
        patch.object(agent_service.template_service, "get_active_templates", return_value=_TEMPLATES),
        patch.object(agent_service.designer_service, "get_designer_options", return_value=_OPTIONS),
        patch.object(agent_service.anthropic, "Anthropic") as mock_anthropic_cls,
        patch.object(agent_service, "supabase") as mock_supabase,
        patch.object(agent_service.order_service, "create_order") as mock_create_order,
        patch.object(agent_service.order_service, "get_order_by_id", return_value={"id": "order-1", "status": "pending"}),
        patch.object(agent_service.notification_service, "create_notification_for_order_event") as mock_notify,
    ):
        mock_anthropic_cls.return_value.messages.create.return_value = _fake_claude_response(**claude_fields)
        mock_supabase.table.return_value.insert.return_value.execute.return_value = _mock_insert_result()
        if create_order_side_effect is not None:
            mock_create_order.side_effect = create_order_side_effect
        else:
            mock_create_order.return_value = "order-1"

        result = agent_service.run_order_assistant_turn(message, draft, _CUSTOMER)

    return result, mock_create_order, mock_notify


# --- Missing fields are requested -------------------------------------------


def test_missing_fields_are_requested_no_order_created():
    result, mock_create_order, _ = _run(
        "I'd like to order a cake",
        None,
        {"reply": "Great! What size, flavor, filling, and frosting would you like, and a phone number for the order?"},
    )

    assert result["order_created"] is False
    assert result["order_id"] is None
    assert result["draft"] == {"templateId": None, "cakeSizeId": None, "flavorId": None, "fillingId": None, "frostingId": None, "phone": None}
    assert "size" in result["reply"].lower() or "flavor" in result["reply"].lower()
    mock_create_order.assert_not_called()


def test_partial_extraction_updates_draft_and_still_asks_for_the_rest():
    result, mock_create_order, _ = _run(
        "I'd like the Classic Vanilla in medium",
        None,
        {"templateId": "tpl-1", "cakeSizeId": "size-1", "reply": "Got it -- what flavor, filling, and frosting?"},
    )

    assert result["draft"]["templateId"] == "tpl-1"
    assert result["draft"]["cakeSizeId"] == "size-1"
    assert result["draft"]["flavorId"] is None  # still missing, not guessed
    mock_create_order.assert_not_called()


def test_hallucinated_id_is_rejected_not_trusted():
    # Claude returns an id that doesn't exist in the real catalog --
    # must be ignored, never written into the draft.
    result, mock_create_order, _ = _run(
        "I'd like the Deluxe Unicorn cake",
        None,
        {"templateId": "tpl-does-not-exist", "reply": "I couldn't find that design -- here's what we offer..."},
    )

    assert result["draft"]["templateId"] is None
    mock_create_order.assert_not_called()


# --- No order created before explicit confirmation --------------------------


def test_no_order_created_when_confirmed_now_true_but_message_does_not_look_like_confirmation():
    # Defense in depth: even if Claude's own confirmedNow says true, the
    # independent _looks_like_confirmation check on the raw message must
    # also pass -- a message like a plain question must never trigger it.
    result, mock_create_order, _ = _run(
        "What's the total price?",
        _COMPLETE_DRAFT,
        {"confirmedNow": True, "reply": "The total comes to $45."},
    )

    assert result["order_created"] is False
    mock_create_order.assert_not_called()


def test_no_order_created_when_fields_still_missing_even_if_message_looks_like_confirmation():
    incomplete_draft = {**_COMPLETE_DRAFT, "phone": None}
    result, mock_create_order, _ = _run(
        "Yes, please confirm",
        incomplete_draft,
        {"confirmedNow": True, "reply": "I still need your phone number."},
    )

    assert result["order_created"] is False
    mock_create_order.assert_not_called()


# --- Confirmed + complete calls the existing order service -----------------


def test_confirmed_complete_order_calls_the_existing_order_service():
    result, mock_create_order, mock_notify = _run(
        "Yes, please create my order",
        _COMPLETE_DRAFT,
        {"confirmedNow": True, "reply": "Ignored -- app writes its own confirmation text."},
    )

    assert result["order_created"] is True
    assert result["order_id"] == "order-1"
    assert "order-1" in result["reply"]
    mock_create_order.assert_called_once_with(
        {
            "template_id": "tpl-1",
            "cake_size_id": "size-1",
            "flavor_id": "flav-1",
            "filling_id": "fill-1",
            "frosting_id": "frost-1",
            "customer_name": "Jane Doe",
            "customer_phone": "+15551234567",
            "customer_email": "jane@example.com",
        }
    )
    mock_notify.assert_called_once()
    # Draft is cleared once the order actually exists -- nothing left to collect.
    assert result["draft"] == {"templateId": None, "cakeSizeId": None, "flavorId": None, "fillingId": None, "frostingId": None, "phone": None}


def test_created_order_associated_with_the_correct_customer():
    other_customer = {"id": "cust-2", "name": "Amir Cohen", "email": "amir@example.com"}
    with (
        patch.object(agent_service.settings, "anthropic_api_key", "fake-key-for-test"),
        patch.object(agent_service.template_service, "get_active_templates", return_value=_TEMPLATES),
        patch.object(agent_service.designer_service, "get_designer_options", return_value=_OPTIONS),
        patch.object(agent_service.anthropic, "Anthropic") as mock_anthropic_cls,
        patch.object(agent_service, "supabase") as mock_supabase,
        patch.object(agent_service.order_service, "create_order", return_value="order-2") as mock_create_order,
        patch.object(agent_service.order_service, "get_order_by_id", return_value={"id": "order-2"}),
        patch.object(agent_service.notification_service, "create_notification_for_order_event"),
    ):
        mock_anthropic_cls.return_value.messages.create.return_value = _fake_claude_response(confirmedNow=True)
        mock_supabase.table.return_value.insert.return_value.execute.return_value = _mock_insert_result()

        agent_service.run_order_assistant_turn("Yes, confirm", _COMPLETE_DRAFT, other_customer)

    payload = mock_create_order.call_args.args[0]
    assert payload["customer_name"] == "Amir Cohen"
    assert payload["customer_email"] == "amir@example.com"


# --- Failure returns a safe message without duplicate order creation -------


def test_order_creation_failure_returns_safe_message_no_duplicate_creation():
    result, mock_create_order, _ = _run(
        "Yes, please create my order",
        _COMPLETE_DRAFT,
        {"confirmedNow": True},
        create_order_side_effect=ValueError("Invalid cake size, flavor, filling, or frosting selection"),
    )

    assert result["order_created"] is False
    assert result["order_id"] is None
    assert "wrong" in result["reply"].lower() or "sorry" in result["reply"].lower()
    mock_create_order.assert_called_once()  # attempted exactly once, never retried


def test_claude_call_failure_returns_safe_message_and_unchanged_draft():
    with (
        patch.object(agent_service.settings, "anthropic_api_key", "fake-key-for-test"),
        patch.object(agent_service.template_service, "get_active_templates", return_value=_TEMPLATES),
        patch.object(agent_service.designer_service, "get_designer_options", return_value=_OPTIONS),
        patch.object(agent_service.anthropic, "Anthropic") as mock_anthropic_cls,
        patch.object(agent_service, "supabase") as mock_supabase,
        patch.object(agent_service.order_service, "create_order") as mock_create_order,
    ):
        mock_anthropic_cls.return_value.messages.create.side_effect = RuntimeError("Anthropic API down")
        mock_supabase.table.return_value.insert.return_value.execute.return_value = _mock_insert_result()

        result = agent_service.run_order_assistant_turn("I'd like to order a cake", None, _CUSTOMER)

    assert result["ai_status"] == "failed"
    assert result["order_created"] is False
    mock_create_order.assert_not_called()


def test_not_configured_returns_safe_message_without_calling_claude_or_catalog():
    with (
        patch.object(agent_service.settings, "anthropic_api_key", None),
        patch.object(agent_service.template_service, "get_active_templates") as mock_templates,
        patch.object(agent_service.anthropic, "Anthropic") as mock_anthropic_cls,
    ):
        result = agent_service.run_order_assistant_turn("I'd like to order a cake", None, _CUSTOMER)

    assert result["order_created"] is False
    assert result["ai_status"] == "failed"
    mock_templates.assert_not_called()
    mock_anthropic_cls.assert_not_called()


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
