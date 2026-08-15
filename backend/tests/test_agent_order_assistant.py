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
    {"id": "tpl-1", "name": "Classic Vanilla", "category": "Birthday", "base_price": 45.0, "active": True},
    {"id": "tpl-2", "name": "Chocolate Confetti Celebration", "category": "Birthday", "base_price": 52.0, "active": True},
]
_OPTIONS = {
    "cake_sizes": [
        {"id": "size-1", "name": "Small", "price_adjustment": 0, "servings_min": 8, "servings_max": 10},
        {"id": "size-2", "name": "Medium", "price_adjustment": 50, "servings_min": 12, "servings_max": 15},
        {"id": "size-3", "name": "Large", "price_adjustment": 100, "servings_min": 18, "servings_max": 22},
    ],
    "flavors": [{"id": "flav-1", "name": "Chocolate"}],
    "fillings": [{"id": "fill-1", "name": "Chocolate Ganache"}],
    "frostings": [{"id": "frost-1", "name": "Buttercream"}, {"id": "frost-2", "name": "Dark Chocolate Ganache"}],
}
_LARGE_SIZE_ID = "size-3"
_MEDIUM_SIZE_ID = "size-2"

# The exact reported-bug configuration: Chocolate Confetti Celebration /
# Large / Chocolate / Chocolate Ganache / Dark Chocolate Ganache -- a real,
# valid catalog combination (confirmed against production data before this
# fix, see the commit message), used by the size-regression and
# create_order regression tests below.
_REPORTED_BUG_DRAFT = {
    "templateId": "tpl-2",
    "cakeSizeId": _LARGE_SIZE_ID,
    "flavorId": "flav-1",
    "fillingId": "fill-1",
    "frostingId": "frost-2",
    "phone": "+972545446601",
}

_COMPLETE_DRAFT = {
    "templateId": "tpl-1",
    "cakeSizeId": "size-1",
    "flavorId": "flav-1",
    "fillingId": "fill-1",
    "frostingId": "frost-1",
    "phone": "+15551234567",
}

# The FINAL CONFIRMATION bug report's configuration: 15 guests -> Medium,
# Classic Vanilla Birthday, phone valid. Flavor/filling/frosting reuse this
# file's existing fixture ids (Red Velvet/Lemon Curd aren't in the fixture
# catalog) -- irrelevant to the confirmation-gate mechanism under test,
# which never looks at flavor choice, only at whether every field is known.
_MEDIUM_CONFIRMATION_DRAFT = {
    "templateId": "tpl-1",
    "cakeSizeId": _MEDIUM_SIZE_ID,
    "flavorId": "flav-1",
    "fillingId": "fill-1",
    "frostingId": "frost-1",
    "phone": "+972545446601",
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
    agent_service._catalog_cache.clear()  # this file's tests all run within one TTL window -- see that cache's own note
    with (
        patch.object(agent_service.settings, "anthropic_api_key", "fake-key-for-test"),
        patch.object(agent_service.template_service, "get_active_templates", return_value=_TEMPLATES),
        patch.object(agent_service.designer_service, "get_designer_options", return_value=_OPTIONS),
        patch.object(agent_service.anthropic, "Anthropic") as mock_anthropic_cls,
        patch.object(agent_service, "supabase") as mock_supabase,
        patch.object(agent_service.order_service, "create_order") as mock_create_order,
        # Only consulted when a pickup date was actually captured (for the
        # rush-warning check) -- a real, unmocked no-op for every existing
        # test here, which never sets one.
        patch.object(agent_service.order_service, "get_template_by_id", return_value=_TEMPLATES[0]),
        patch.object(
            agent_service.order_service, "get_order_by_id",
            return_value={"id": "order-1", "status": "pending", "total_price": 152.0},
        ),
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
    assert result["draft"] == {
        "templateId": None, "cakeSizeId": None, "flavorId": None, "fillingId": None,
        "frostingId": None, "phone": None, "specialRequestNote": None,
        "pickupDate": None, "pickupTime": None,
        "awaitingOrderConfirmation": False,
    }
    assert "size" in result["reply"].lower() or "flavor" in result["reply"].lower()
    mock_create_order.assert_not_called()


def test_partial_extraction_updates_draft_and_still_asks_for_the_rest():
    # cakeSizeId is deterministic (see _explicit_size_change): the customer
    # literally said "medium" here, so Python resolves the real Medium id
    # itself -- Claude's own (here mismatched, size-1/Small) cakeSizeId
    # candidate is never trusted directly, by design (see Bug #1's fix).
    result, mock_create_order, _, _sb = _run(
        "I'd like the Classic Vanilla in medium",
        None,
        {"templateId": "tpl-1", "cakeSizeId": "size-1", "reply": "Got it -- what flavor, filling, and frosting?"},
    )

    assert result["draft"]["templateId"] == "tpl-1"
    assert result["draft"]["cakeSizeId"] == "size-2"  # real Medium, from the customer's own word, not Claude's id
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
            # Regression: create_order() requires a "notes" key (KeyError
            # otherwise -- see Bug #2's fix); None is the real, valid,
            # "nothing special noted" value.
            "notes": None,
        },
        # Pickup Date + Order Priority, Phase 2: optional in chat -- None
        # here since _COMPLETE_DRAFT never stated one, same "not yet
        # known" contract as every other unset field.
        pickup_date=None,
        pickup_time=None,
    )
    mock_notify.assert_called_once()
    # Draft is cleared once the order actually exists -- nothing left to collect.
    assert result["draft"] == {
        "templateId": None, "cakeSizeId": None, "flavorId": None, "fillingId": None,
        "frostingId": None, "phone": None, "specialRequestNote": None,
        "pickupDate": None, "pickupTime": None,
        "awaitingOrderConfirmation": False,
    }


def test_created_order_associated_with_the_correct_customer():
    other_customer = {"id": "cust-2", "name": "Amir Cohen", "email": "amir@example.com"}
    agent_service._catalog_cache.clear()
    with (
        patch.object(agent_service.settings, "anthropic_api_key", "fake-key-for-test"),
        patch.object(agent_service.template_service, "get_active_templates", return_value=_TEMPLATES),
        patch.object(agent_service.designer_service, "get_designer_options", return_value=_OPTIONS),
        patch.object(agent_service.anthropic, "Anthropic") as mock_anthropic_cls,
        patch.object(agent_service, "supabase") as mock_supabase,
        patch.object(agent_service.order_service, "create_order", return_value="order-2") as mock_create_order,
        patch.object(agent_service.order_service, "get_order_by_id", return_value={"id": "order-2", "total_price": 45.0}),
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
    agent_service._catalog_cache.clear()
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


# --- "Start an order" click auto-fires the first turn (chat-widget.js) ------
# The widget now calls this with message == trigger_context (the same
# customer message that earned the nudge, see startOrderingMode's own note)
# instead of waiting for the customer to type again.


def test_first_turn_with_message_equal_to_trigger_context_seeds_size_and_creates_no_order():
    trigger = "I would like to order a birthday cake for 20 people."
    result, mock_create_order, _, _sb = _run(
        trigger,
        None,  # fresh draft -- this is the very first turn, exactly what the click fires
        {"reply": "Perfect -- let's build your birthday cake. Which design would you like?"},
        trigger_context=trigger,
    )
    assert result["draft"]["cakeSizeId"] == _LARGE_SIZE_ID
    assert result["order_created"] is False
    assert result["order_id"] is None
    mock_create_order.assert_not_called()


def test_first_turn_prompt_already_shows_the_seeded_size_and_real_catalog_before_claude_is_asked():
    # Proves size is filled in the "ORDER SO FAR" section *before* the
    # prompt is built -- Claude is told it's already known, not left to
    # infer it, and the real Birthday catalog is right there too, so the
    # reply can list real options instead of asking again.
    trigger = "I would like to order a birthday cake for 20 people."
    agent_service._catalog_cache.clear()
    with (
        patch.object(agent_service.settings, "anthropic_api_key", "fake-key-for-test"),
        patch.object(agent_service.template_service, "get_active_templates", return_value=_TEMPLATES),
        patch.object(agent_service.designer_service, "get_designer_options", return_value=_OPTIONS),
        patch.object(agent_service.anthropic, "Anthropic") as mock_anthropic_cls,
        patch.object(agent_service, "supabase") as mock_supabase,
    ):
        mock_anthropic_cls.return_value.messages.create.return_value = _fake_claude_response(
            reply="Which design would you like?"
        )
        mock_supabase.table.return_value.insert.return_value.execute.return_value = _mock_insert_result()

        agent_service.run_order_assistant_turn(trigger, None, _CUSTOMER, trigger_context=trigger)

    sent_prompt = mock_anthropic_cls.return_value.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "Large" in sent_prompt  # already in ORDER SO FAR, not left for Claude to ask
    for template in _TEMPLATES:  # real Birthday catalog available to answer with
        assert template["id"] in sent_prompt
        assert template["name"] in sent_prompt


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
    assert result["draft"] == {
        **partial_draft, "specialRequestNote": None, "pickupDate": None, "pickupTime": None,
        "awaitingOrderConfirmation": False,
    }  # nothing lost
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
    agent_service._catalog_cache.clear()
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


# --- Production bug fix: size regression, create_order KeyError, payment
# and rush-availability hallucination (see the commit message for the full
# live reproduction of each). All four fixes share the exact reported,
# valid catalog configuration (_REPORTED_BUG_DRAFT) so these tests double
# as a faithful replay of the real conversation.


def test_large_survives_a_design_selection_even_if_claude_returns_medium():
    draft = {**_REPORTED_BUG_DRAFT, "templateId": None, "flavorId": None, "fillingId": None, "frostingId": None, "phone": None}
    result, _, _, _sb = _run(
        "I'll go with the Chocolate Confetti Celebration",
        draft,
        {
            "templateId": "tpl-2",
            "cakeSizeId": _MEDIUM_SIZE_ID,  # simulates Claude mis-recalling the size on this turn
            "reply": "Great choice! What flavor, filling, and frosting?",
        },
    )
    assert result["draft"]["cakeSizeId"] == _LARGE_SIZE_ID
    assert result["draft"]["templateId"] == "tpl-2"


def test_large_survives_flavor_filling_frosting_selection_even_if_claude_returns_medium():
    draft = {**_REPORTED_BUG_DRAFT, "flavorId": None, "fillingId": None, "frostingId": None, "phone": None}
    result, _, _, _sb = _run(
        "Chocolate, Chocolate Ganache, and Dark Chocolate Ganache please",
        draft,
        {
            "flavorId": "flav-1", "fillingId": "fill-1", "frostingId": "frost-2",
            "cakeSizeId": _MEDIUM_SIZE_ID,
            "reply": "Got it -- and your phone number?",
        },
    )
    assert result["draft"]["cakeSizeId"] == _LARGE_SIZE_ID
    assert result["draft"]["flavorId"] == "flav-1"
    assert result["draft"]["fillingId"] == "fill-1"
    assert result["draft"]["frostingId"] == "frost-2"


def test_large_survives_the_exact_reported_price_and_availability_question():
    # The exact turn that regressed size in production: everything already
    # selected, customer asks about price/availability -- the message says
    # nothing about size at all -- yet Claude's own cakeSizeId candidate
    # came back Medium (a real id, so the old code trusted it outright).
    draft = {**_REPORTED_BUG_DRAFT, "phone": None}
    result, mock_create_order, _, _sb = _run(
        "what is the price and can it be ready tomorrow?",
        draft,
        {
            "cakeSizeId": _MEDIUM_SIZE_ID,
            "asksAboutPrice": True,
            "specialRequestNote": "customer asked if ready by tomorrow",
            "reply": "Sure thing!",
        },
    )
    assert result["draft"]["cakeSizeId"] == _LARGE_SIZE_ID  # never regressed to Medium
    expected_price = agent_service._compute_order_price(_REPORTED_BUG_DRAFT, _TEMPLATES, _OPTIONS)
    assert f"${expected_price:.2f}" in result["reply"]
    assert "$102.00" not in result["reply"]  # the wrong, Medium-based figure from the real bug report
    assert result["draft"]["specialRequestNote"] == "customer asked if ready by tomorrow"
    mock_create_order.assert_not_called()  # an informational question must never create an order


def test_compute_order_price_for_the_reported_configuration_uses_large_not_medium():
    large_price = agent_service._compute_order_price(_REPORTED_BUG_DRAFT, _TEMPLATES, _OPTIONS)
    medium_price = agent_service._compute_order_price({**_REPORTED_BUG_DRAFT, "cakeSizeId": _MEDIUM_SIZE_ID}, _TEMPLATES, _OPTIONS)
    assert large_price != medium_price
    assert large_price == _TEMPLATES[1]["base_price"] + _OPTIONS["cake_sizes"][2]["price_adjustment"]


def test_confirmation_and_phone_in_the_same_message_creates_the_order_when_everything_else_is_known():
    # Confirmation Gate policy's own named example.
    draft = {**_REPORTED_BUG_DRAFT, "phone": None}
    result, mock_create_order, _, _sb = _run(
        "confirmed and my phone number is: +972545446601",
        draft,
        {"phone": "+972545446601", "confirmedNow": True, "reply": "..."},
    )
    assert result["order_created"] is True
    mock_create_order.assert_called_once()
    assert mock_create_order.call_args.args[0]["customer_phone"] == "+972545446601"


def test_local_phone_format_normalized_by_claude_passes_through_to_create_order():
    # There is no dedicated phone-normalization utility in this codebase --
    # Claude itself normalizes a local Israeli mobile number to E.164
    # (matching the bug report's own observation that this part already
    # worked correctly in production); Python trusts whatever string Claude
    # returns for phone verbatim, unchanged by this fix. The message also
    # restates "20 people", which independently reinforces (not regresses)
    # the already-locked Large size.
    draft = {**_REPORTED_BUG_DRAFT, "phone": None}
    result, mock_create_order, _, _sb = _run(
        "Yep, for 20 people and my phone number is 0545446601",
        draft,
        {"phone": "+972545446601", "confirmedNow": True, "reply": "..."},
    )
    assert result["order_created"] is True
    assert mock_create_order.call_args.args[0]["customer_phone"] == "+972545446601"
    assert mock_create_order.call_args.args[0]["cake_size_id"] == _LARGE_SIZE_ID  # never regressed to Medium


def test_full_valid_confirmed_payload_reaches_create_order_exactly_once():
    result, mock_create_order, mock_notify, _sb = _run(
        "yes and confirmed. Do I pay now?",
        _REPORTED_BUG_DRAFT,
        {"confirmedNow": True, "reply": "..."},
    )
    assert result["order_created"] is True
    assert result["order_id"] == "order-1"
    mock_create_order.assert_called_once_with(
        {
            "template_id": "tpl-2",
            "cake_size_id": _LARGE_SIZE_ID,
            "flavor_id": "flav-1",
            "filling_id": "fill-1",
            "frosting_id": "frost-2",
            "customer_name": "Jane Doe",
            "customer_phone": "+972545446601",
            "customer_email": "jane@example.com",
            "notes": None,
        },
        pickup_date=None,
        pickup_time=None,
    )
    mock_notify.assert_called_once()


def test_reported_create_order_failure_is_reproduced_and_fixed():
    # Bug #2's exact root cause: order_service.create_order() unconditionally
    # reads order["notes"], but the payload built above never included that
    # key -- a real KeyError('notes'), caught by run_order_assistant_turn's
    # broad except, surfaced as "something went wrong creating your order"
    # (see this file's _run harness for every OTHER test, which mocks
    # create_order entirely -- this one deliberately lets the REAL function
    # run, so it would have failed against the pre-fix code).
    agent_service._catalog_cache.clear()
    with (
        patch.object(agent_service.settings, "anthropic_api_key", "fake-key-for-test"),
        patch.object(agent_service.template_service, "get_active_templates", return_value=_TEMPLATES),
        patch.object(agent_service.designer_service, "get_designer_options", return_value=_OPTIONS),
        patch.object(agent_service.anthropic, "Anthropic") as mock_anthropic_cls,
        patch.object(agent_service, "supabase") as mock_supabase,
        patch.object(agent_service.order_service, "get_template_by_id", return_value=_TEMPLATES[1]),
        patch.object(agent_service.order_service, "get_designer_options", return_value=_OPTIONS),
        patch.object(agent_service.order_service, "find_or_create_customer", return_value="cust-1"),
        patch.object(agent_service.order_service, "supabase") as mock_order_supabase,
        patch.object(
            agent_service.order_service, "get_order_by_id",
            return_value={"id": "order-real-1", "status": "pending", "total_price": 152.0},
        ),
        patch.object(agent_service.notification_service, "create_notification_for_order_event"),
    ):
        mock_anthropic_cls.return_value.messages.create.return_value = _fake_claude_response(confirmedNow=True)
        mock_supabase.table.return_value.insert.return_value.execute.return_value = _mock_insert_result()
        mock_order_supabase.table.return_value.insert.return_value.execute.return_value = SimpleNamespace(
            data=[{"id": "order-real-1"}]
        )

        result = agent_service.run_order_assistant_turn(
            "yes and confirmed. Do I pay now?", _REPORTED_BUG_DRAFT, _CUSTOMER,
        )

    assert result["order_created"] is True
    assert result["order_id"] == "order-real-1"
    assert "order-real-1" in result["reply"]


def test_failed_order_creation_preserves_the_full_reported_draft_untouched():
    result, mock_create_order, _, _sb = _run(
        "yes and confirmed. Do I pay now?",
        _REPORTED_BUG_DRAFT,
        {"confirmedNow": True, "reply": "..."},
        create_order_side_effect=RuntimeError("transient DB error"),
    )
    assert result["order_created"] is False
    assert result["draft"] == {
        **_REPORTED_BUG_DRAFT, "specialRequestNote": None, "pickupDate": None, "pickupTime": None,
        "awaitingOrderConfirmation": False,
    }
    mock_create_order.assert_called_once()


def test_repeated_confirmation_after_success_does_not_create_a_duplicate_order():
    result1, mock_create_order_1, _, _sb1 = _run(
        "yes and confirmed",
        _REPORTED_BUG_DRAFT,
        {"confirmedNow": True, "reply": "..."},
    )
    assert result1["order_created"] is True
    empty_draft = result1["draft"]  # reset once the order actually exists

    result2, mock_create_order_2, _, _sb2 = _run(
        "yes confirmed again",
        empty_draft,
        {"confirmedNow": True, "reply": "..."},
    )
    assert result2["order_created"] is False
    mock_create_order_2.assert_not_called()


def test_prompt_forbids_claiming_in_chat_payment_or_checkout():
    catalog_text, _names = agent_service._build_order_catalog(_TEMPLATES, _OPTIONS)
    prompt = agent_service._order_assistant_prompt(
        "how can I pay? can I pay now?", agent_service._normalize_order_draft(None), catalog_text, ""
    )
    lowered = " ".join(prompt.lower().split())  # collapse the prompt's own line wraps for a stable substring check
    assert "no payment, credit card, or checkout capability" in lowered
    assert "payment is arranged with the bakery" in lowered


def test_prompt_forbids_promising_rush_availability_and_captures_it_as_a_note():
    catalog_text, _names = agent_service._build_order_catalog(_TEMPLATES, _OPTIONS)
    prompt = agent_service._order_assistant_prompt(
        "can it be ready tomorrow?", agent_service._normalize_order_draft(None), catalog_text, ""
    )
    assert "do not promise or guess availability" in prompt.lower()
    assert "specialrequestnote" in prompt.lower()


# --- Payment is a separate, explicit customer action -----------------------
# Order confirmation and payment are two distinct actions (see this
# module's own note on run_order_assistant_turn's success branch): a
# freshly-created order must always come back Pending, offering the next
# step, never auto-paid.


def test_chat_order_creation_does_not_automatically_trigger_payment():
    with patch.object(agent_service, "payment_service") as mock_payment_service:
        result, mock_create_order, _, _sb = _run(
            "yes and confirmed. Do I pay now?",
            _REPORTED_BUG_DRAFT,
            {"confirmedNow": True, "reply": "..."},
        )

    assert result["order_created"] is True
    mock_payment_service.simulate_payment.assert_not_called()
    lowered = result["reply"].lower()
    assert "payment: pending" in lowered
    # Payment is the next required step, not a new decision to weigh --
    # never asked as a question (see this function's own note).
    assert "would you like" not in lowered
    assert "complete the simulated payment" in lowered


def test_chat_order_created_reply_includes_the_real_authoritative_total():
    # total_price comes from the real, freshly-fetched order row (get_
    # order_by_id) -- the same orders.total_price payment_service.
    # simulate_payment will later charge (simulated) against -- never a
    # separately recomputed or Claude-stated number.
    result, _, _, _sb = _run(
        "yes and confirmed. Do I pay now?",
        _REPORTED_BUG_DRAFT,
        {"confirmedNow": True, "reply": "..."},
    )
    assert "$152.00" in result["reply"]


def test_whatsapp_order_creation_does_not_automatically_trigger_payment():
    with patch.object(agent_service, "payment_service") as mock_payment_service:
        result, mock_create_order, _, _sb = _run(
            "yes and confirmed. Do I pay now?",
            _REPORTED_BUG_DRAFT,
            {"confirmedNow": True, "reply": "..."},
            channel="whatsapp",
        )

    assert result["order_created"] is True
    mock_payment_service.simulate_payment.assert_not_called()
    assert "payment: pending" in result["reply"].lower()


def test_whatsapp_order_created_reply_points_to_the_real_website_payment_page():
    # WhatsApp has no button surface -- it gets the real payment.html link
    # for the order instead of attempting an in-thread card flow (see this
    # module's own note on why). Never requests card details in the reply.
    result, _, _, _sb = _run(
        "yes and confirmed. Do I pay now?",
        _REPORTED_BUG_DRAFT,
        {"confirmedNow": True, "reply": "..."},
        channel="whatsapp",
    )
    assert f"{agent_service._CUSTOMER_SITE_BASE}/payment.html?order=order-1" in result["reply"]
    lowered = result["reply"].lower()
    assert "card" not in lowered
    assert "cvv" not in lowered


# --- FINAL CONFIRMATION policy: contextual confirmation, no false claims --
# Reproduces the exact reported production loop: all fields known, final
# summary shown, "great" correctly doesn't confirm, but "please do" --
# answering the assistant's own "shall I place this order?" -- should have
# confirmed on the first try. It didn't (keyword-list gap), and the reply
# claimed the order was "on its way to being placed" even though Python's
# own gate never created it. Both are fixed below: "please do" is now a
# recognized keyword, and a Claude/Python disagreement can never reach the
# customer as a false success claim.


def test_reported_confirmation_loop_please_do_confirms_after_final_summary():
    # Turn 1: everything already known, Claude doesn't itself confirm --
    # this turn's own outcome must record that it just asked to confirm.
    turn1, mock_create_order_1, _, _sb1 = _run(
        "great",
        _MEDIUM_CONFIRMATION_DRAFT,
        {"reply": "Everything looks great! Shall I place this order?"},
    )
    assert turn1["order_created"] is False
    assert turn1["draft"]["awaitingOrderConfirmation"] is True
    mock_create_order_1.assert_not_called()

    # Turn 2: "please do", answering that exact question.
    turn2, mock_create_order_2, mock_notify, _sb2 = _run(
        "please do",
        turn1["draft"],
        {"confirmedNow": True, "reply": "..."},
    )
    assert turn2["order_created"] is True
    assert turn2["order_id"] == "order-1"
    mock_create_order_2.assert_called_once()  # exactly once
    mock_notify.assert_called_once()
    # Payment is never automatic -- a real, separate customer action.
    assert "payment: pending" in turn2["reply"].lower()
    assert "would you like" not in turn2["reply"].lower()


def test_unambiguous_affirmatives_confirm_when_awaiting_final_confirmation():
    awaiting_draft = {**_MEDIUM_CONFIRMATION_DRAFT, "awaitingOrderConfirmation": True}
    for phrase in ("yes", "yes please", "please do", "go ahead", "place it", "confirmed"):
        result, mock_create_order, _, _sb = _run(
            phrase, awaiting_draft, {"confirmedNow": True, "reply": "..."},
        )
        assert result["order_created"] is True, f"{phrase!r} should have confirmed"
        mock_create_order.assert_called_once()


def test_ambiguous_standalone_replies_never_confirm_even_while_awaiting_confirmation():
    # Section 3's hard rule: "great"/"perfect"/"ok"/"thanks" must never
    # confirm, even in the awaiting-confirmation context, even if (as
    # simulated here) Claude itself wrongly agrees -- the fixed keyword
    # list is the deterministic backstop context can never bypass.
    awaiting_draft = {**_MEDIUM_CONFIRMATION_DRAFT, "awaitingOrderConfirmation": True}
    for phrase in ("great", "perfect", "ok", "thanks"):
        result, mock_create_order, _, _sb = _run(
            phrase, awaiting_draft, {"confirmedNow": True, "reply": "..."},
        )
        assert result["order_created"] is False, f"{phrase!r} must not confirm"
        mock_create_order.assert_not_called()


def test_reply_never_claims_success_when_claude_believes_confirmed_but_python_disagrees():
    # A future keyword-list gap, simulated directly: Claude judges
    # confirmedNow=true for a phrase not in the deterministic list. Python
    # must still reject it, AND Claude's premature "it's being placed"
    # text must never reach the customer.
    result, mock_create_order, _, _sb = _run(
        "sure thing",
        _MEDIUM_CONFIRMATION_DRAFT,
        {"confirmedNow": True, "reply": "Great news -- your cake is on its way to being placed!"},
    )
    assert result["order_created"] is False
    mock_create_order.assert_not_called()
    assert "on its way to being placed" not in result["reply"]
    assert "confirm" in result["reply"].lower()  # the honest, prospective re-ask instead


def test_confirmation_cannot_succeed_before_all_fields_are_known():
    incomplete_draft = {**_MEDIUM_CONFIRMATION_DRAFT, "phone": None, "awaitingOrderConfirmation": True}
    result, mock_create_order, _, _sb = _run(
        "please do", incomplete_draft, {"confirmedNow": True, "reply": "..."},
    )
    assert result["order_created"] is False
    mock_create_order.assert_not_called()


def test_repeated_please_do_after_success_does_not_duplicate_the_order():
    awaiting_draft = {**_MEDIUM_CONFIRMATION_DRAFT, "awaitingOrderConfirmation": True}
    turn1, mock_create_order_1, _, _sb1 = _run("please do", awaiting_draft, {"confirmedNow": True, "reply": "..."})
    assert turn1["order_created"] is True

    turn2, mock_create_order_2, _, _sb2 = _run("please do", turn1["draft"], {"confirmedNow": True, "reply": "..."})
    assert turn2["order_created"] is False
    mock_create_order_2.assert_not_called()


def test_prompt_includes_awaiting_confirmation_note_only_when_flagged():
    catalog_text, _names = agent_service._build_order_catalog(_TEMPLATES, _OPTIONS)
    normalized = agent_service._normalize_order_draft(_MEDIUM_CONFIRMATION_DRAFT)
    prompt_with = agent_service._order_assistant_prompt(
        "please do", normalized, catalog_text, "", awaiting_confirmation=True,
    )
    prompt_without = agent_service._order_assistant_prompt(
        "please do", normalized, catalog_text, "", awaiting_confirmation=False,
    )
    assert "already asked the customer to confirm this exact order" in prompt_with
    assert "already asked the customer to confirm this exact order" not in prompt_without


def test_pending_order_reply_recaps_the_real_cake_selections():
    # The post-creation message now shows what was actually ordered
    # (design/size/flavor/filling/frosting), not just the order id/total
    # -- all from the real, already-known draft/catalog data, nothing new
    # fetched or invented.
    result, _, _, _sb = _run(
        "please do",
        {**_MEDIUM_CONFIRMATION_DRAFT, "awaitingOrderConfirmation": True},
        {"confirmedNow": True, "reply": "..."},
    )
    assert result["order_created"] is True
    assert "Classic Vanilla" in result["reply"]
    assert "Medium — serves 12-15" in result["reply"]
    assert "Chocolate" in result["reply"]  # flavor
    assert "Buttercream" in result["reply"]  # frosting


# --- Final Customer Policy Pass: mandatory allergy confirmation (F/G/H) ----
# Two independent, deterministic behaviors, neither trusted to Claude:
# (1) a disclosed food allergy blocks automated ordering outright, on any
#     turn, before Claude is even called;
# (2) once the order is otherwise complete, the mandatory allergy
#     confirmation is deterministically folded into the same final "shall
#     I place this order?" ask -- Python-appended text, not dependent on
#     Claude's own prompt-following.


def test_allergy_mention_bypasses_claude_and_blocks_order_creation():
    with (
        patch.object(agent_service.settings, "anthropic_api_key", "fake-key-for-test"),
        patch.object(agent_service.anthropic, "Anthropic") as mock_anthropic_cls,
        patch.object(agent_service, "supabase") as mock_supabase,
        patch.object(agent_service.order_service, "create_order") as mock_create_order,
    ):
        mock_supabase.table.return_value.insert.return_value.execute.return_value = _mock_insert_result()
        result = agent_service.run_order_assistant_turn(
            "I have a nut allergy, can I still order the chocolate cake?", None, _CUSTOMER,
        )

    mock_anthropic_cls.assert_not_called()  # Claude never gets a chance to decide it's safe
    mock_create_order.assert_not_called()
    assert result["order_created"] is False
    assert result["order_id"] is None
    assert result["reply"] == agent_service._ALLERGY_ORDER_BLOCKED_MESSAGE
    assert "contact us directly" in result["reply"].lower()


def test_allergy_mention_at_the_final_confirmation_step_still_blocks_the_order():
    # Even when every field is already known and the message otherwise
    # reads like a confirmation, a disclosed allergy wins -- Claude never
    # gets to "approve an exception".
    awaiting_draft = {**_MEDIUM_CONFIRMATION_DRAFT, "awaitingOrderConfirmation": True}
    result, mock_create_order, mock_notify, _sb = _run(
        "yes please go ahead, though I do have an egg allergy",
        awaiting_draft,
        {"confirmedNow": True, "reply": "should never be seen"},
    )
    assert result["order_created"] is False
    mock_create_order.assert_not_called()
    mock_notify.assert_not_called()
    assert result["reply"] == agent_service._ALLERGY_ORDER_BLOCKED_MESSAGE


def test_final_summary_deterministically_includes_the_allergy_confirmation():
    # All fields known, not yet confirmed -- Python appends the mandatory
    # allergy line itself, regardless of what Claude's own "reply" says.
    result, mock_create_order, _, _sb = _run(
        "great", _MEDIUM_CONFIRMATION_DRAFT, {"reply": "Everything looks great! Shall I place this order?"},
    )
    assert result["order_created"] is False
    mock_create_order.assert_not_called()
    assert "food allerg" in result["reply"].lower()


def test_allergy_confirmation_is_not_repeated_in_the_success_message():
    # Once genuinely confirmed, the order-created message fully replaces
    # reply_text (same as the price note) -- the allergy line only belongs
    # in the pre-confirmation ask, not the post-creation summary.
    awaiting_draft = {**_MEDIUM_CONFIRMATION_DRAFT, "awaitingOrderConfirmation": True}
    result, mock_create_order, _, _sb = _run(
        "please do", awaiting_draft, {"confirmedNow": True, "reply": "..."},
    )
    assert result["order_created"] is True
    mock_create_order.assert_called_once()
    assert "food allerg" not in result["reply"].lower()


# --- Pickup Date + Order Priority, Phase 2: optional chat capture ----------


def _next_weekday_iso(target_weekday, *, at_least_days_out=7):
    from datetime import datetime, timedelta, timezone

    candidate = datetime.now(timezone.utc).date() + timedelta(days=at_least_days_out)
    while candidate.weekday() != target_weekday:
        candidate += timedelta(days=1)
    return candidate.isoformat()


def test_valid_pickup_date_and_time_are_captured_into_the_draft():
    tuesday = _next_weekday_iso(1)  # 1 = Tuesday
    result, _mock_create_order, _, _sb = _run(
        "Tuesday at noon works for me",
        None,
        {"pickupDate": tuesday, "pickupTime": "12:00", "reply": "Got it — Tuesday at noon."},
    )
    assert result["draft"]["pickupDate"] == tuesday
    assert result["draft"]["pickupTime"] == "12:00:00"  # time.isoformat() always includes seconds


def test_monday_pickup_proposed_by_claude_is_never_trusted():
    # Same "propose, Python decides" posture as every other field -- an
    # invalid business-rule violation from Claude's own extraction must
    # never reach the draft, exactly like an unrecognized catalog id.
    monday = _next_weekday_iso(0)  # 0 = Monday
    result, _mock_create_order, _, _sb = _run(
        "Monday at noon please",
        None,
        {"pickupDate": monday, "pickupTime": "12:00", "reply": "..."},
    )
    assert result["draft"]["pickupDate"] is None
    assert result["draft"]["pickupTime"] is None


def test_malformed_pickup_date_from_claude_is_dropped_not_crashed():
    result, _mock_create_order, _, _sb = _run(
        "next Blursday maybe?",
        None,
        {"pickupDate": "not-a-real-date", "pickupTime": "noon-ish", "reply": "..."},
    )
    assert result["draft"]["pickupDate"] is None
    assert result["draft"]["pickupTime"] is None


def test_order_still_confirms_without_any_pickup_date_stated():
    # The deliberate scope decision for Phase 2: pickup scheduling is
    # mandatory on the Website form, but stays OPTIONAL in chat rather
    # than becoming a new hard gate on the existing, heavily-tested
    # confirmation flow (see run_order_assistant_turn's own note).
    result, mock_create_order, _, _sb = _run(
        "Yes, please create my order",
        _COMPLETE_DRAFT,
        {"confirmedNow": True, "reply": "..."},
    )
    assert result["order_created"] is True
    mock_create_order.assert_called_once()
    assert mock_create_order.call_args.kwargs == {"pickup_date": None, "pickup_time": None}


def test_confirmed_order_with_known_pickup_passes_it_through_to_create_order():
    tuesday = _next_weekday_iso(1, at_least_days_out=60)  # well outside every category's rush window
    draft = {**_COMPLETE_DRAFT, "pickupDate": tuesday, "pickupTime": "12:00"}
    result, mock_create_order, _, _sb = _run(
        "Yes, please create my order", draft, {"confirmedNow": True, "reply": "..."},
    )
    assert result["order_created"] is True
    assert mock_create_order.call_args.kwargs == {"pickup_date": tuesday, "pickup_time": "12:00"}
    # Outside the rush window (Birthday's 2-day minimum) -- notes stays untouched.
    assert mock_create_order.call_args.args[0]["notes"] is None


def test_confirmed_order_with_rush_pickup_gets_the_warning_appended_to_notes():
    from datetime import datetime, timedelta, timezone

    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
    draft = {**_COMPLETE_DRAFT, "pickupDate": tomorrow, "pickupTime": "12:00"}
    result, mock_create_order, _, _sb = _run(
        "Yes, please create my order", draft, {"confirmedNow": True, "reply": "..."},
    )
    assert result["order_created"] is True
    notes = mock_create_order.call_args.args[0]["notes"]
    assert notes is not None and "rush" in notes.lower()


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
