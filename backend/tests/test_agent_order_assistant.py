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

_TEMPLATES = [
    {"id": "tpl-1", "name": "Classic Vanilla", "category": "Birthday", "base_price": 45.0},
    {"id": "tpl-2", "name": "Chocolate Confetti Celebration", "category": "Birthday", "base_price": 52.0},
]
_OPTIONS = {
    "cake_sizes": [
        {"id": "size-1", "name": "Small", "price_adjustment": 0, "servings_min": 8, "servings_max": 10},
        {"id": "size-2", "name": "Medium", "price_adjustment": 50, "servings_min": 12, "servings_max": 15},
        {"id": "size-3", "name": "Large", "price_adjustment": 100, "servings_min": 18, "servings_max": 22},
    ],
    "flavors": [{"id": "flav-1", "name": "Chocolate"}],
    "fillings": [{"id": "fill-1", "name": "Chocolate Ganache"}],
    "frostings": [{"id": "frost-1", "name": "Buttercream"}],
}
_LARGE_SIZE_ID = "size-3"

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


def _run(
    message,
    draft,
    claude_fields,
    *,
    create_order_side_effect=None,
    trigger_context=None,
    claude_side_effect=None,
    channel="chat",
    conversation_history=None,
):
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
        if claude_side_effect is not None:
            mock_anthropic_cls.return_value.messages.create.side_effect = claude_side_effect
        else:
            mock_anthropic_cls.return_value.messages.create.return_value = _fake_claude_response(**claude_fields)
        mock_supabase.table.return_value.insert.return_value.execute.return_value = _mock_insert_result()
        if create_order_side_effect is not None:
            mock_create_order.side_effect = create_order_side_effect
        else:
            mock_create_order.return_value = "order-1"

        result = agent_service.run_order_assistant_turn(
            message, draft, _CUSTOMER, trigger_context=trigger_context,
            conversation_history=conversation_history, channel=channel,
        )

    return result, mock_create_order, mock_notify, mock_supabase


# --- Missing fields are requested -------------------------------------------


def test_missing_fields_are_requested_no_order_created():
    result, mock_create_order, _, _sb = _run(
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
    result, mock_create_order, _, _sb = _run(
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
    result, mock_create_order, _, _sb = _run(
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
    result, mock_create_order, _, _sb = _run(
        "What's the total price?",
        _COMPLETE_DRAFT,
        {"confirmedNow": True, "reply": "The total comes to $45."},
    )

    assert result["order_created"] is False
    mock_create_order.assert_not_called()


def test_no_order_created_when_fields_still_missing_even_if_message_looks_like_confirmation():
    incomplete_draft = {**_COMPLETE_DRAFT, "phone": None}
    result, mock_create_order, _, _sb = _run(
        "Yes, please confirm",
        incomplete_draft,
        {"confirmedNow": True, "reply": "I still need your phone number."},
    )

    assert result["order_created"] is False
    mock_create_order.assert_not_called()


# --- Confirmed + complete calls the existing order service -----------------


def test_confirmed_complete_order_calls_the_existing_order_service():
    result, mock_create_order, mock_notify, _sb = _run(
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
    result, mock_create_order, _, _sb = _run(
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


# --- Live-bug regression: multi-part turn (selection + question + price) --
# Reproduced live against the real Anthropic API before this fix (not
# guessed): the old max_tokens=500 budget truncated Claude's JSON output
# mid-string while it tried to enumerate the entire 15-template catalog
# in response to "other designs", producing unparseable JSON and the
# generic "Sorry, I had trouble with that" fallback. See the commit
# message for the exact reproduction and raw truncated output.


def test_multi_slot_turn_with_design_question_and_price_question_does_not_crash():
    result, mock_create_order, _, _sb = _run(
        "i would like to hear about other disigned , and i already mention few times that it is for 20 "
        "people. filling - Chocolate Ganache and frosting ,Buttercream, and how nuch is the cost of this cack?",
        None,
        {
            "fillingId": "fill-1",
            "frostingId": "frost-1",
            "asksAboutPrice": True,
            "reply": "Noted! Here are a couple of birthday designs: Classic Vanilla, Chocolate Confetti Celebration.",
        },
    )

    assert result["ai_status"] == "drafted"
    assert result["draft"]["fillingId"] == "fill-1"  # Chocolate Ganache retained
    assert result["draft"]["frostingId"] == "frost-1"  # Buttercream retained
    mock_create_order.assert_not_called()  # not a confirmation -- must not create anything


# --- Guest count -> real size (the /chat/ask -> /chat/order handoff) -------


def test_extract_guest_count_handles_real_phrasing_variants():
    assert agent_service._extract_guest_count("I would like to order a birthday cake for 20 nice people") == 20
    assert agent_service._extract_guest_count("it is for 20 people") == 20
    assert agent_service._extract_guest_count("a cake for 25 guests") == 25
    assert agent_service._extract_guest_count("no number mentioned here") is None


def test_size_for_guest_count_maps_to_the_real_catalog_range():
    assert agent_service._size_for_guest_count(20, _OPTIONS["cake_sizes"]) == _LARGE_SIZE_ID
    assert agent_service._size_for_guest_count(9, _OPTIONS["cake_sizes"]) == "size-1"
    assert agent_service._size_for_guest_count(1000, _OPTIONS["cake_sizes"]) is None  # no guessing the closest one


def test_trigger_context_seeds_the_correct_size_on_the_first_turn_only():
    result, _, _, _sb = _run(
        "chocolate cake which will look impressive",
        None,  # fresh draft -- the seed only ever applies here
        {"reply": "Great choice! What flavor, filling, frosting, and phone number?"},
        trigger_context="I would like to order a birthday cake for 20 nice people",
    )
    assert result["draft"]["cakeSizeId"] == _LARGE_SIZE_ID


def test_trigger_context_is_ignored_once_the_draft_already_has_something():
    # Only ever consulted on a genuinely fresh draft (the frontend sends
    # it exactly once, see chat-widget.js's own note) -- a non-empty
    # incoming draft's own already-collected size must not be silently
    # overridden by a stale trigger context on a later turn.
    draft_with_a_different_size_already_chosen = {**_COMPLETE_DRAFT, "cakeSizeId": "size-1"}
    result, _, _, _sb = _run(
        "actually let's go with chocolate",
        draft_with_a_different_size_already_chosen,
        {"reply": "Got it."},
        trigger_context="a cake for 20 people",
    )
    assert result["draft"]["cakeSizeId"] == "size-1"


# --- Design discovery -------------------------------------------------------


def test_prompt_constrains_design_listing_to_the_real_catalog_only():
    catalog_text, _names = agent_service._build_order_catalog(_TEMPLATES, _OPTIONS)
    prompt = agent_service._order_assistant_prompt(
        "what other designs do you have?", agent_service._normalize_order_draft(None), catalog_text, ""
    )

    assert "AT MOST 4" in prompt
    assert "never list the whole catalog" in prompt
    for template in _TEMPLATES:
        assert template["id"] in prompt
        assert template["name"] in prompt


def test_design_discovery_reply_reaches_the_customer_unmodified():
    result, _, _, _sb = _run(
        "what other designs do you have?",
        None,
        {"reply": "We also have Chocolate Confetti Celebration and Classic Vanilla for birthdays!"},
    )
    assert "Chocolate Confetti Celebration" in result["reply"]


# --- Price: never hallucinated, only from real catalog math ----------------


def test_price_question_appends_the_real_computed_total_not_claudes_own_number():
    result, _, _, _sb = _run(
        "how much would this cost?",
        {**_COMPLETE_DRAFT, "templateId": "tpl-1", "cakeSizeId": _LARGE_SIZE_ID},
        {"asksAboutPrice": True, "reply": "Great question!"},
    )
    # tpl-1 base_price 45.0 + Large's price_adjustment 100 = 145.00 -- the
    # exact real catalog arithmetic order_service.create_order() itself
    # uses (base_price + size.price_adjustment only).
    assert "$145.00" in result["reply"]


def test_exact_price_returned_only_when_template_and_size_are_both_known():
    result, _, _, _sb = _run(
        "how much would this cost?",
        {**_COMPLETE_DRAFT, "templateId": "tpl-2", "cakeSizeId": "size-1"},
        {"asksAboutPrice": True, "reply": "Sure!"},
    )
    assert "$52.00" in result["reply"]  # tpl-2 base_price 52.0 + Small's 0 adjustment


def test_missing_price_dependency_is_explained_not_guessed():
    design_not_chosen_yet = {**_COMPLETE_DRAFT, "templateId": None}
    result, _, _, _sb = _run(
        "how much would this cost?",
        design_not_chosen_yet,
        {"asksAboutPrice": True, "reply": "Happy to help!"},
    )
    assert "$" not in result["reply"]  # no number invented
    assert "design and size" in result["reply"]


# --- Slots survive an informational question, and the confirmation gate ----
# stays exactly as strict as before (Claude's confirmedNow, every field
# filled, AND the raw message independently looking like a "yes" -- all
# three, unweakened by any of the above).


def test_collected_slots_survive_a_purely_informational_question():
    draft_with_filling_and_frosting_already_known = {
        "templateId": None, "cakeSizeId": None, "flavorId": None,
        "fillingId": "fill-1", "frostingId": "frost-1", "phone": None,
    }
    result, mock_create_order, _, _sb = _run(
        "what other designs do you have?",
        draft_with_filling_and_frosting_already_known,
        {"reply": "Here are a couple of options: Classic Vanilla, Chocolate Confetti Celebration."},
    )
    assert result["draft"]["fillingId"] == "fill-1"
    assert result["draft"]["frostingId"] == "frost-1"
    mock_create_order.assert_not_called()


def test_no_order_created_for_the_exact_reported_multi_part_message():
    result, mock_create_order, _, _sb = _run(
        "i would like to hear about other disigned , and i already mention few times that it is for 20 "
        "people. filling - Chocolate Ganache and frosting ,Buttercream, and how nuch is the cost of this cack?",
        None,
        {"fillingId": "fill-1", "frostingId": "frost-1", "asksAboutPrice": True, "confirmedNow": False, "reply": "..."},
    )
    assert result["order_created"] is False
    mock_create_order.assert_not_called()


# --- Failure path: safe reply, draft never lost -----------------------------


def test_failure_path_preserves_a_non_empty_incoming_draft():
    partial_draft = {**_COMPLETE_DRAFT, "phone": None}  # a real, in-progress draft
    result, mock_create_order, _, _sb = _run(
        "how much would this cost?",
        partial_draft,
        {},
        claude_side_effect=RuntimeError("Anthropic API down"),
    )
    assert result["ai_status"] == "failed"
    assert result["reply"]
    assert result["order_created"] is False
    assert result["draft"] == partial_draft  # nothing lost
    mock_create_order.assert_not_called()


# --- Unsupported / custom requests (Final Ordering Policy, Section 8) ------


def test_prompt_instructs_closest_real_alternatives_for_unsupported_requests():
    catalog_text, _names = agent_service._build_order_catalog(_TEMPLATES, _OPTIONS)
    prompt = agent_service._order_assistant_prompt(
        "I want something completely different, not in your list",
        agent_service._normalize_order_draft(None), catalog_text, "",
    )
    assert "do NOT invent it or pretend it's available" in prompt
    assert "closest 2-4 real options" in prompt


def test_unsupported_request_reply_offers_real_options_not_a_fabricated_one():
    result, mock_create_order, _, _sb = _run(
        "can you combine two different designs into one?",
        None,
        {"reply": "We can't combine designs, but here are close real options: Classic Vanilla, Chocolate Confetti Celebration."},
    )
    assert "Classic Vanilla" in result["reply"]
    mock_create_order.assert_not_called()


# --- Confirmation gate precision (Final Ordering Policy, Section 10) -------
# The exact non-confirmations and confirmations the policy calls out by
# name -- "Great."/"I like that."/"How much?" must never trigger
# creation even if Claude's own confirmedNow says true; "Yes, create my
# order."/"Confirm the order." must.


def test_vague_acknowledgments_never_trigger_confirmation_even_if_claude_says_so():
    for non_confirmation in ("Looks good.", "I like that.", "How much?", "Great.", "Perfect."):
        result, mock_create_order, _, _sb = _run(
            non_confirmation, _COMPLETE_DRAFT, {"confirmedNow": True, "reply": "..."},
        )
        assert result["order_created"] is False, f"{non_confirmation!r} incorrectly triggered order creation"
        mock_create_order.assert_not_called()


def test_explicit_confirmation_phrases_from_the_policy_do_trigger_creation():
    for confirmation in ("Yes, create my order.", "Yes, please place it.", "Confirm the order."):
        result, mock_create_order, _, _sb = _run(
            confirmation, _COMPLETE_DRAFT, {"confirmedNow": True, "reply": "..."},
        )
        assert result["order_created"] is True, f"{confirmation!r} should have triggered order creation"
        mock_create_order.assert_called_once()


# --- WhatsApp channel: shared logic, different persistence -----------------
# Same run_order_assistant_turn, same triple confirmation gate, same
# price/catalog protection -- only channel="whatsapp" changes, and only
# in how the reply is persisted (draft for a human to send, never sent
# automatically -- see the function's own docstring).


def test_whatsapp_channel_persists_the_reply_as_a_draft_not_sent():
    _result, _mock_create_order, _mock_notify, mock_supabase = _run(
        "what other designs do you have?", None, {"reply": "Here are a couple: Classic Vanilla, Chocolate Confetti Celebration."},
        channel="whatsapp",
    )
    inserted_payload = mock_supabase.table.return_value.insert.call_args.args[0]
    assert inserted_payload["status"] == "draft"  # never sent automatically
    assert inserted_payload["channel"] == "whatsapp"
    assert inserted_payload["event"] == "agent_drafted"  # the existing draft/approval event, not a new one


def test_chat_channel_still_persists_the_reply_as_already_sent():
    # Regression check: adding the whatsapp path must not change chat's
    # existing "already reached the customer" behavior.
    _result, _mock_create_order, _mock_notify, mock_supabase = _run(
        "what other designs do you have?", None, {"reply": "Here are a couple: Classic Vanilla, Chocolate Confetti Celebration."},
        channel="chat",
    )
    inserted_payload = mock_supabase.table.return_value.insert.call_args.args[0]
    assert inserted_payload["status"] == "sent"
    assert inserted_payload["channel"] == "chat"


def test_whatsapp_confirmation_gate_is_identical_to_chat():
    result, mock_create_order, _, _sb = _run(
        "Yes, create my order.", _COMPLETE_DRAFT, {"confirmedNow": True, "reply": "..."}, channel="whatsapp",
    )
    assert result["order_created"] is True
    mock_create_order.assert_called_once()


def test_whatsapp_never_creates_order_without_confirmation_even_mid_conversation():
    result, mock_create_order, _, _sb = _run(
        "what's the total?", _COMPLETE_DRAFT, {"asksAboutPrice": True, "confirmedNow": False, "reply": "..."},
        channel="whatsapp",
    )
    assert result["order_created"] is False
    mock_create_order.assert_not_called()


def test_conversation_history_is_folded_into_the_prompt_for_whatsapp():
    history = [
        {"direction": "incoming", "body": "I want a birthday cake for 20 people", "timestamp": "t1"},
        {"direction": "outgoing", "body": "Great, what design would you like?", "timestamp": "t2"},
    ]
    with (
        patch.object(agent_service.settings, "anthropic_api_key", "fake-key-for-test"),
        patch.object(agent_service.template_service, "get_active_templates", return_value=_TEMPLATES),
        patch.object(agent_service.designer_service, "get_designer_options", return_value=_OPTIONS),
        patch.object(agent_service.anthropic, "Anthropic") as mock_anthropic_cls,
        patch.object(agent_service, "supabase") as mock_supabase,
    ):
        mock_anthropic_cls.return_value.messages.create.return_value = _fake_claude_response(reply="...")
        mock_supabase.table.return_value.insert.return_value.execute.return_value = _mock_insert_result()

        agent_service.run_order_assistant_turn(
            "Chocolate Ganache please", None, _CUSTOMER, channel="whatsapp", conversation_history=history,
        )

    sent_prompt = mock_anthropic_cls.return_value.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "I want a birthday cake for 20 people" in sent_prompt


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
