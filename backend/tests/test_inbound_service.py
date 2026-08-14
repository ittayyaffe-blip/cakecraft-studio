"""Dependency-free self-check for inbound_service.py — no network/DB/
Anthropic API call required. Run from `backend/`:

    python -m tests.test_inbound_service

Mocks the exact I/O boundary (supabase, plus the customer_service/
order_service/agent_service functions this module calls into) — the real
customer/order-matching decision logic and orchestration run for real
against fixed inputs. draft_reply_to_inbound_message()'s own grounding
behavior is covered separately in test_agent_service.py; here the concern
is purely "did inbound_service wire the right pieces together with the
right data" — customer identification, order matching, idempotency,
never inventing an identity.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services import inbound_service
from app.services.communication import twilio_whatsapp_inbound

FAKE_CUSTOMER = {"id": "cust-1", "name": "Jane Doe", "email": "jane@example.com", "phone": "+33612345678"}
FAKE_ORDER = {
    "id": "order-1",
    "status": "in_progress",
    "cake_templates": {"name": "Rose Cake", "category": "Birthday"},
    "pickup_date": None,
}


def _fake_inbound_row(**overrides):
    row = {
        "id": "inbound-1",
        "channel": "email",
        "provider_message_id": "<msg-1@x>",
        "sender_identifier": "jane@example.com",
        "subject": "Question",
        "body": "Can I change my cake size?",
        "received_at": datetime.now(timezone.utc).isoformat(),
        "thread_id": None,
        "customer_id": None,
        "order_id": None,
        "order_match_status": "none",
        "ai_status": "pending",
        "draft_notification_id": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    row.update(overrides)
    return row


def _self_chaining_query_mock(execute_result):
    query = MagicMock()
    for method in ("select", "eq", "lt", "insert", "update", "is_", "order", "limit", "maybe_single"):
        getattr(query, method).return_value = query
    query.execute.return_value = execute_result
    return query


def _make_supabase_mock(*execute_results):
    """supabase.table(...) returns a fresh self-chaining query mock each
    call, in order — matches inbound_service.py's own call pattern (find
    existing, then insert, then update), each step needing a different
    execute() result.
    """
    mock_supabase = MagicMock()
    queries = [_self_chaining_query_mock(result) for result in execute_results]
    mock_supabase.table.side_effect = queries
    return mock_supabase, queries


# --- Idempotency / duplicate message handling -------------------------------


def test_process_inbound_email_is_idempotent_for_a_repeated_message_id():
    existing_row = _fake_inbound_row()
    query = _self_chaining_query_mock(SimpleNamespace(data=existing_row))
    with patch.object(inbound_service, "supabase") as mock_supabase:
        mock_supabase.table.return_value = query
        parsed = {
            "sender_email": "jane@example.com",
            "subject": "Question",
            "body": "Can I change my cake size?",
            "message_id": "<msg-1@x>",
            "thread_id": None,
            "received_at": datetime.now(timezone.utc),
        }
        result = inbound_service.process_inbound_email(parsed)

    assert result == existing_row
    query.insert.assert_not_called()


def test_process_inbound_whatsapp_is_idempotent_for_a_repeated_message_id():
    existing_row = _fake_inbound_row(channel="whatsapp", provider_message_id="wamid.123", sender_identifier="33612345678")
    query = _self_chaining_query_mock(SimpleNamespace(data=existing_row))
    with patch.object(inbound_service, "supabase") as mock_supabase:
        mock_supabase.table.return_value = query
        parsed = {"sender_phone": "33612345678", "body": "Is my cake ready?", "message_id": "wamid.123", "timestamp_epoch": None}
        result = inbound_service.process_inbound_whatsapp(parsed)

    assert result == existing_row
    query.insert.assert_not_called()


def test_twilio_parsed_payload_is_accepted_by_the_unmodified_whatsapp_pipeline():
    # The actual contract proof: a real (not hand-written) dict produced
    # by twilio_whatsapp_inbound.parse_webhook_payload -- Twilio's own
    # provider, a completely different module -- is accepted by
    # process_inbound_whatsapp with no shape mismatch, exactly like a
    # Meta-parsed dict already is. This function itself is untouched by
    # the Twilio integration; this test is what actually proves that
    # claim rather than just asserting it in a docstring.
    existing_row = _fake_inbound_row(channel="whatsapp", provider_message_id="SMabc123", sender_identifier="+33612345678")
    query = _self_chaining_query_mock(SimpleNamespace(data=existing_row))
    with patch.object(inbound_service, "supabase") as mock_supabase:
        mock_supabase.table.return_value = query
        parsed = twilio_whatsapp_inbound.parse_webhook_payload(
            {"From": "whatsapp:+33612345678", "Body": "Is my cake ready?", "MessageSid": "SMabc123"}
        )
        assert parsed is not None  # a real parse failure would silently no-op the test otherwise
        result = inbound_service.process_inbound_whatsapp(parsed)

    assert result == existing_row
    query.insert.assert_not_called()


# --- Customer matching: known / unknown / ambiguous -------------------------


def test_known_customer_with_matched_order_creates_a_draft():
    mock_supabase, queries = _make_supabase_mock(
        SimpleNamespace(data=None),  # find existing: not found
        SimpleNamespace(data=[_fake_inbound_row()]),  # insert
        SimpleNamespace(data=[]),  # get_recent_conversation: no prior messages
        SimpleNamespace(  # update
            data=[
                _fake_inbound_row(
                    customer_id="cust-1", order_id="order-1", order_match_status="matched",
                    ai_status="drafted", draft_notification_id="notif-1",
                )
            ]
        ),
    )
    parsed = {
        "sender_email": "jane@example.com", "subject": "Question", "body": "Can I change my cake size?",
        "message_id": "<msg-1@x>", "thread_id": None, "received_at": datetime.now(timezone.utc),
    }

    with (
        patch.object(inbound_service, "supabase", mock_supabase),
        patch.object(inbound_service, "customer_service") as mock_customer_service,
        patch.object(inbound_service, "order_service") as mock_order_service,
        patch.object(inbound_service, "agent_service") as mock_agent_service,
    ):
        mock_customer_service.find_customer_by_email.return_value = (FAKE_CUSTOMER, False)
        mock_order_service.find_open_order_for_customer.return_value = (FAKE_ORDER, "matched")
        mock_agent_service.draft_reply_to_inbound_message.return_value = {
            "ai_status": "drafted", "notification": {"id": "notif-1"}
        }

        result = inbound_service.process_inbound_email(parsed)

    mock_customer_service.find_customer_by_email.assert_called_once_with("jane@example.com")
    mock_order_service.find_open_order_for_customer.assert_called_once_with("cust-1")
    mock_agent_service.draft_reply_to_inbound_message.assert_called_once()

    update_payload = queries[3].update.call_args.args[0]
    assert update_payload["customer_id"] == "cust-1"
    assert update_payload["order_id"] == "order-1"
    assert update_payload["order_match_status"] == "matched"
    assert update_payload["ai_status"] == "drafted"
    assert update_payload["draft_notification_id"] == "notif-1"
    assert result["ai_status"] == "drafted"


def test_unknown_customer_leaves_message_visible_with_no_draft():
    mock_supabase, queries = _make_supabase_mock(
        SimpleNamespace(data=None),
        SimpleNamespace(data=[_fake_inbound_row()]),
        SimpleNamespace(data=[_fake_inbound_row(ai_status="failed")]),
    )
    parsed = {
        "sender_email": "stranger@example.com", "subject": None, "body": "Hi there",
        "message_id": "<msg-2@x>", "thread_id": None, "received_at": datetime.now(timezone.utc),
    }

    with (
        patch.object(inbound_service, "supabase", mock_supabase),
        patch.object(inbound_service, "customer_service") as mock_customer_service,
        patch.object(inbound_service, "agent_service") as mock_agent_service,
    ):
        mock_customer_service.find_customer_by_email.return_value = (None, False)
        result = inbound_service.process_inbound_email(parsed)

    # The system must never invent a customer identity -- no AI drafting
    # is even attempted without a real customer_id to attach a draft to.
    mock_agent_service.draft_reply_to_inbound_message.assert_not_called()
    update_payload = queries[2].update.call_args.args[0]
    assert update_payload == {"ai_status": "failed"}
    assert result["ai_status"] == "failed"


def test_ambiguous_customer_match_also_does_not_guess():
    mock_supabase, queries = _make_supabase_mock(
        SimpleNamespace(data=None),
        SimpleNamespace(data=[_fake_inbound_row()]),
        SimpleNamespace(data=[_fake_inbound_row(ai_status="failed")]),
    )
    parsed = {
        "sender_email": "shared@example.com", "subject": None, "body": "Hi",
        "message_id": "<msg-3@x>", "thread_id": None, "received_at": datetime.now(timezone.utc),
    }

    with (
        patch.object(inbound_service, "supabase", mock_supabase),
        patch.object(inbound_service, "customer_service") as mock_customer_service,
        patch.object(inbound_service, "agent_service") as mock_agent_service,
    ):
        # More than one customer row shares this email -- ambiguous, not "unknown".
        mock_customer_service.find_customer_by_email.return_value = (None, True)
        inbound_service.process_inbound_email(parsed)

    mock_agent_service.draft_reply_to_inbound_message.assert_not_called()
    update_payload = queries[2].update.call_args.args[0]
    assert update_payload == {"ai_status": "failed"}


# --- Order matching: one match / multiple (ambiguous) / none ---------------


def test_no_matching_order_still_drafts_with_a_null_order():
    mock_supabase, queries = _make_supabase_mock(
        SimpleNamespace(data=None),
        SimpleNamespace(data=[_fake_inbound_row()]),
        SimpleNamespace(data=[]),  # get_recent_conversation: no prior messages
        SimpleNamespace(
            data=[_fake_inbound_row(customer_id="cust-1", order_match_status="none", ai_status="drafted", draft_notification_id="notif-2")]
        ),
    )
    parsed = {
        "sender_email": "jane@example.com", "subject": None, "body": "What flavors do you have?",
        "message_id": "<msg-4@x>", "thread_id": None, "received_at": datetime.now(timezone.utc),
    }

    with (
        patch.object(inbound_service, "supabase", mock_supabase),
        patch.object(inbound_service, "customer_service") as mock_customer_service,
        patch.object(inbound_service, "order_service") as mock_order_service,
        patch.object(inbound_service, "agent_service") as mock_agent_service,
    ):
        mock_customer_service.find_customer_by_email.return_value = (FAKE_CUSTOMER, False)
        mock_order_service.find_open_order_for_customer.return_value = (None, "none")
        mock_agent_service.draft_reply_to_inbound_message.return_value = {
            "ai_status": "drafted", "notification": {"id": "notif-2"}
        }

        inbound_service.process_inbound_email(parsed)

    # order=None must be passed through to the AI Agent explicitly, not
    # skipped or replaced with a guess.
    call_args = mock_agent_service.draft_reply_to_inbound_message.call_args
    assert call_args.args[2] is None
    update_payload = queries[3].update.call_args.args[0]
    assert update_payload["order_id"] is None
    assert update_payload["order_match_status"] == "none"


def test_multiple_open_orders_marks_ambiguous_and_does_not_guess_one():
    mock_supabase, queries = _make_supabase_mock(
        SimpleNamespace(data=None),
        SimpleNamespace(data=[_fake_inbound_row()]),
        SimpleNamespace(data=[]),  # get_recent_conversation: no prior messages
        SimpleNamespace(
            data=[_fake_inbound_row(customer_id="cust-1", order_match_status="ambiguous", ai_status="unable_to_answer")]
        ),
    )
    parsed = {
        "sender_email": "jane@example.com", "subject": None, "body": "Can I change my order?",
        "message_id": "<msg-5@x>", "thread_id": None, "received_at": datetime.now(timezone.utc),
    }

    with (
        patch.object(inbound_service, "supabase", mock_supabase),
        patch.object(inbound_service, "customer_service") as mock_customer_service,
        patch.object(inbound_service, "order_service") as mock_order_service,
        patch.object(inbound_service, "agent_service") as mock_agent_service,
    ):
        mock_customer_service.find_customer_by_email.return_value = (FAKE_CUSTOMER, False)
        mock_order_service.find_open_order_for_customer.return_value = (None, "ambiguous")
        mock_agent_service.draft_reply_to_inbound_message.return_value = {
            "ai_status": "unable_to_answer", "notification": {"id": "notif-3"}
        }

        inbound_service.process_inbound_email(parsed)

    call_args = mock_agent_service.draft_reply_to_inbound_message.call_args
    assert call_args.args[2] is None  # no order guessed, even though several exist
    update_payload = queries[3].update.call_args.args[0]
    assert update_payload["order_match_status"] == "ambiguous"
    assert update_payload["order_id"] is None


# --- Channel routing: Email uses email lookup, WhatsApp uses phone lookup --


def test_whatsapp_message_uses_phone_lookup_not_email_lookup():
    mock_supabase, queries = _make_supabase_mock(
        SimpleNamespace(data=None),
        SimpleNamespace(data=[_fake_inbound_row(channel="whatsapp", sender_identifier="+33 6 12 34 56 78")]),
        SimpleNamespace(data=[]),  # get_recent_conversation: no prior messages
        SimpleNamespace(
            data=[
                _fake_inbound_row(
                    channel="whatsapp", sender_identifier="+33 6 12 34 56 78",
                    customer_id="cust-1", ai_status="drafted", draft_notification_id="notif-4",
                )
            ]
        ),
    )
    parsed = {"sender_phone": "+33 6 12 34 56 78", "body": "Is my cake ready?", "message_id": "wamid.999", "timestamp_epoch": None}

    with (
        patch.object(inbound_service, "supabase", mock_supabase),
        patch.object(inbound_service, "customer_service") as mock_customer_service,
        patch.object(inbound_service, "order_service") as mock_order_service,
        patch.object(inbound_service, "agent_service") as mock_agent_service,
    ):
        mock_customer_service.find_customer_by_phone.return_value = (FAKE_CUSTOMER, False)
        mock_order_service.find_open_order_for_customer.return_value = (FAKE_ORDER, "matched")
        mock_agent_service.draft_reply_to_inbound_message.return_value = {
            "ai_status": "drafted", "notification": {"id": "notif-4"}
        }

        inbound_service.process_inbound_whatsapp(parsed)

    mock_customer_service.find_customer_by_phone.assert_called_once_with("+33 6 12 34 56 78")
    mock_customer_service.find_customer_by_email.assert_not_called()
    # The channel handed to the AI Agent comes from the inbound row
    # (application-controlled), never inferred by the AI itself.
    inbound_arg = mock_agent_service.draft_reply_to_inbound_message.call_args.args[0]
    assert inbound_arg["channel"] == "whatsapp"


# --- Step 3B: conversation history + intent/handling wiring ----------------


def test_get_recent_conversation_scopes_to_one_customer_and_excludes_current_message():
    prior = [
        {"body": "I love chocolate!", "received_at": "2026-08-08T10:00:00Z", "created_at": "2026-08-08T10:00:00Z"},
    ]
    query = _self_chaining_query_mock(SimpleNamespace(data=prior))
    with patch.object(inbound_service, "supabase") as mock_supabase:
        mock_supabase.table.return_value = query
        history = inbound_service.get_recent_conversation("cust-1", before_created_at="2026-08-09T10:00:00Z")

    query.eq.assert_any_call("customer_id", "cust-1")
    query.lt.assert_any_call("created_at", "2026-08-09T10:00:00Z")
    assert history == prior


def test_get_recent_conversation_empty_for_a_first_time_sender():
    query = _self_chaining_query_mock(SimpleNamespace(data=[]))
    with patch.object(inbound_service, "supabase") as mock_supabase:
        mock_supabase.table.return_value = query
        history = inbound_service.get_recent_conversation("cust-1", before_created_at="2026-08-09T10:00:00Z")
    assert history == []


def test_process_and_draft_persists_intent_handling_and_review_reason():
    mock_supabase, queries = _make_supabase_mock(
        SimpleNamespace(data=None),
        SimpleNamespace(data=[_fake_inbound_row()]),
        SimpleNamespace(data=[]),
        SimpleNamespace(
            data=[
                _fake_inbound_row(
                    customer_id="cust-1", order_id="order-1", order_match_status="matched",
                    ai_status="drafted", draft_notification_id="notif-1",
                    intent="ALLERGY_DIETARY", handling="yellow",
                    review_reason="Nut-free guarantee not supported by trusted knowledge.",
                )
            ]
        ),
    )
    parsed = {
        "sender_email": "jane@example.com", "subject": "Allergy question", "body": "Is this nut-free?",
        "message_id": "<msg-6@x>", "thread_id": None, "received_at": datetime.now(timezone.utc),
    }

    with (
        patch.object(inbound_service, "supabase", mock_supabase),
        patch.object(inbound_service, "customer_service") as mock_customer_service,
        patch.object(inbound_service, "order_service") as mock_order_service,
        patch.object(inbound_service, "agent_service") as mock_agent_service,
    ):
        mock_customer_service.find_customer_by_email.return_value = (FAKE_CUSTOMER, False)
        mock_order_service.find_open_order_for_customer.return_value = (FAKE_ORDER, "matched")
        mock_agent_service.draft_reply_to_inbound_message.return_value = {
            "ai_status": "drafted",
            "notification": {"id": "notif-1"},
            "intent": "ALLERGY_DIETARY",
            "handling": "yellow",
            "review_reason": "Nut-free guarantee not supported by trusted knowledge.",
            "knowledge_sources": [{"title": "Allergen Policy", "sourceFile": "allergen.md"}],
        }

        inbound_service.process_inbound_email(parsed)

    update_payload = queries[3].update.call_args.args[0]
    assert update_payload["intent"] == "ALLERGY_DIETARY"
    assert update_payload["handling"] == "yellow"
    assert update_payload["review_reason"] == "Nut-free guarantee not supported by trusted knowledge."
    assert update_payload["knowledge_sources"] == [{"title": "Allergen Policy", "sourceFile": "allergen.md"}]


def test_conversation_history_passed_through_to_agent_service():
    prior = [{"body": "I love chocolate!", "received_at": "2026-08-08T10:00:00Z", "created_at": "2026-08-08T10:00:00Z"}]
    mock_supabase, queries = _make_supabase_mock(
        SimpleNamespace(data=None),
        SimpleNamespace(data=[_fake_inbound_row()]),
        SimpleNamespace(data=prior),
        SimpleNamespace(data=[_fake_inbound_row(customer_id="cust-1", ai_status="drafted", draft_notification_id="notif-1")]),
    )
    parsed = {
        "sender_email": "jane@example.com", "subject": None, "body": "What about the chocolate one?",
        "message_id": "<msg-7@x>", "thread_id": None, "received_at": datetime.now(timezone.utc),
    }

    with (
        patch.object(inbound_service, "supabase", mock_supabase),
        patch.object(inbound_service, "customer_service") as mock_customer_service,
        patch.object(inbound_service, "order_service") as mock_order_service,
        patch.object(inbound_service, "agent_service") as mock_agent_service,
    ):
        mock_customer_service.find_customer_by_email.return_value = (FAKE_CUSTOMER, False)
        mock_order_service.find_open_order_for_customer.return_value = (None, "none")
        mock_agent_service.draft_reply_to_inbound_message.return_value = {
            "ai_status": "drafted", "notification": {"id": "notif-1"}, "intent": "PRODUCT_QUESTION",
            "handling": "green", "review_reason": None, "knowledge_sources": [],
        }

        inbound_service.process_inbound_email(parsed)

    call_kwargs = mock_agent_service.draft_reply_to_inbound_message.call_args.kwargs
    assert call_kwargs["conversation_history"] == prior


# --- process_order_note: the order form's Notes field as a real inbound ----
# message. FAKE_ORDER_WITH_NOTES mirrors what order_service.get_order_by_id
# returns (see app/api/routes/orders.py's caller) -- the joined shape
# process_order_note expects, with a real customer_id-linked "customers" key.

FAKE_ORDER_WITH_NOTES = {
    "id": "order-9",
    "status": "pending",
    "notes": "Is it a kosher cake?",
    "cake_templates": {"name": "Gold Leaf Romance", "category": "Wedding"},
    "pickup_date": None,
}


def test_process_order_note_blank_notes_creates_nothing():
    for blank in (None, "", "   "):
        order = {**FAKE_ORDER_WITH_NOTES, "notes": blank}
        with patch.object(inbound_service, "supabase") as mock_supabase:
            result = inbound_service.process_order_note(order, FAKE_CUSTOMER)

        assert result is None, f"expected None for notes={blank!r}"
        mock_supabase.table.assert_not_called()  # no DB touched at all


def test_process_order_note_creates_inbound_message_and_drafts():
    mock_supabase, queries = _make_supabase_mock(
        SimpleNamespace(data=None),  # find existing: not found
        SimpleNamespace(data=[_fake_inbound_row(
            channel="email", provider_message_id="order-note:order-9", sender_identifier="jane@example.com",
            subject="Message from order form", body="Is it a kosher cake?",
        )]),  # insert
        SimpleNamespace(data=[]),  # get_recent_conversation: no prior messages
        SimpleNamespace(data=[_fake_inbound_row(
            customer_id="cust-1", order_id="order-9", order_match_status="matched",
            ai_status="drafted", draft_notification_id="notif-kosher",
        )]),  # update
    )

    with (
        patch.object(inbound_service, "supabase", mock_supabase),
        patch.object(inbound_service, "agent_service") as mock_agent_service,
    ):
        mock_agent_service.draft_reply_to_inbound_message.return_value = {
            "ai_status": "drafted", "notification": {"id": "notif-kosher"},
            "intent": "RELIGIOUS_DIETARY", "handling": "red", "review_reason": "Certification not verified.",
            "knowledge_sources": [{"title": "Dietary, Allergy & Religious Requirements Policy", "sourceFile": "x.md"}],
        }
        result = inbound_service.process_order_note(FAKE_ORDER_WITH_NOTES, FAKE_CUSTOMER)

    # Recorded with the exact original text, linked to the real order/customer.
    inserted_payload = queries[1].insert.call_args.args[0]
    assert inserted_payload["channel"] == "email"
    assert inserted_payload["provider_message_id"] == "order-note:order-9"
    assert inserted_payload["sender_identifier"] == FAKE_CUSTOMER["email"]
    assert inserted_payload["body"] == "Is it a kosher cake?"  # preserved exactly, no rewording

    # Entered the same AI Agent / RAG / guardrail pipeline every other
    # channel uses -- customer and order already known, "matched" (not a
    # generic lookup, since this note came in as part of creating this
    # exact order).
    mock_agent_service.draft_reply_to_inbound_message.assert_called_once()
    call_args = mock_agent_service.draft_reply_to_inbound_message.call_args
    assert call_args.args[1] == FAKE_CUSTOMER
    assert call_args.args[2] == FAKE_ORDER_WITH_NOTES
    assert call_args.kwargs["order_match_status"] == "matched"

    update_payload = queries[3].update.call_args.args[0]
    assert update_payload["customer_id"] == "cust-1"
    assert update_payload["order_id"] == "order-9"
    assert update_payload["ai_status"] == "drafted"
    assert result["ai_status"] == "drafted"


def test_process_order_note_is_idempotent():
    # A second call for the same order (retry, double-submit, whatever the
    # trigger) must find the row the (channel, provider_message_id) unique
    # index already protects, not create a duplicate draft.
    existing_row = _fake_inbound_row(
        channel="email", provider_message_id="order-note:order-9",
        ai_status="drafted", draft_notification_id="notif-kosher",
    )
    query = _self_chaining_query_mock(SimpleNamespace(data=existing_row))
    with (
        patch.object(inbound_service, "supabase") as mock_supabase,
        patch.object(inbound_service, "agent_service") as mock_agent_service,
    ):
        mock_supabase.table.return_value = query
        result = inbound_service.process_order_note(FAKE_ORDER_WITH_NOTES, FAKE_CUSTOMER)

    assert result == existing_row
    query.insert.assert_not_called()
    mock_agent_service.draft_reply_to_inbound_message.assert_not_called()


def test_process_order_note_never_raises_on_agent_failure():
    mock_supabase, queries = _make_supabase_mock(
        SimpleNamespace(data=None),
        SimpleNamespace(data=[_fake_inbound_row()]),
        SimpleNamespace(data=[]),
        SimpleNamespace(data=[_fake_inbound_row(ai_status="failed")]),
    )
    with (
        patch.object(inbound_service, "supabase", mock_supabase),
        patch.object(inbound_service, "agent_service") as mock_agent_service,
    ):
        mock_agent_service.draft_reply_to_inbound_message.side_effect = RuntimeError("Anthropic is down")
        result = inbound_service.process_order_note(FAKE_ORDER_WITH_NOTES, FAKE_CUSTOMER)

    assert result is not None  # never raised, never lost the row
    update_payload = queries[3].update.call_args.args[0]
    assert update_payload == {"ai_status": "failed"}


# --- process_chat_message (website live chat widget) -----------------------


def test_process_chat_message_creates_inbound_message_and_returns_answer():
    mock_supabase, queries = _make_supabase_mock(
        SimpleNamespace(data=None),  # find existing: not found (fresh uuid every time)
        SimpleNamespace(data=[_fake_inbound_row(
            channel="email", provider_message_id="chat:whatever", sender_identifier="jane@example.com",
            subject="Website chat question", body="Is it gluten-free?",
        )]),  # insert
        SimpleNamespace(data=[]),  # get_recent_conversation: no prior messages
        SimpleNamespace(data=[_fake_inbound_row(
            customer_id="cust-1", order_id=None, order_match_status="none",
            ai_status="drafted", draft_notification_id="notif-1",
        )]),  # update
    )
    with (
        patch.object(inbound_service, "supabase", mock_supabase),
        patch.object(inbound_service, "agent_service") as mock_agent_service,
    ):
        mock_agent_service.answer_customer_question.return_value = {
            "ai_status": "drafted", "notification": {"id": "notif-1"}, "intent": "ALLERGY_DIETARY",
            "handling": "yellow", "review_reason": None, "knowledge_sources": [], "answer": "Yes, it's gluten-free.",
        }
        result = inbound_service.process_chat_message("Is it gluten-free?", FAKE_CUSTOMER, None, "none")

    inserted_payload = queries[1].insert.call_args.args[0]
    assert inserted_payload["channel"] == "email"  # not a new channel value -- no CHECK-constraint migration
    assert inserted_payload["provider_message_id"].startswith("chat:")
    assert inserted_payload["sender_identifier"] == FAKE_CUSTOMER["email"]
    assert inserted_payload["body"] == "Is it gluten-free?"  # preserved exactly

    mock_agent_service.answer_customer_question.assert_called_once()
    call_args = mock_agent_service.answer_customer_question.call_args
    assert call_args.args[0] == "Is it gluten-free?"
    assert call_args.args[1] == FAKE_CUSTOMER
    assert call_args.args[2] is None
    assert call_args.kwargs["order_match_status"] == "none"

    # The one thing every other inbound_service function does NOT need to
    # return: the answer text itself, for the widget to show right now.
    assert result == {"answer": "Yes, it's gluten-free.", "intent": "ALLERGY_DIETARY", "handling": "yellow"}


def test_process_chat_message_links_the_real_order_when_one_exists():
    mock_supabase, queries = _make_supabase_mock(
        SimpleNamespace(data=None),
        SimpleNamespace(data=[_fake_inbound_row(body="How's my cake coming along?")]),
        SimpleNamespace(data=[]),
        SimpleNamespace(data=[_fake_inbound_row(customer_id="cust-1", order_id="order-1", order_match_status="matched")]),
    )
    with (
        patch.object(inbound_service, "supabase", mock_supabase),
        patch.object(inbound_service, "agent_service") as mock_agent_service,
    ):
        mock_agent_service.answer_customer_question.return_value = {
            "ai_status": "drafted", "notification": {"id": "notif-2"}, "intent": "ORDER_STATUS",
            "handling": "green", "review_reason": None, "knowledge_sources": [], "answer": "It's in progress!",
        }
        inbound_service.process_chat_message("How's my cake coming along?", FAKE_CUSTOMER, FAKE_ORDER, "matched")

    call_args = mock_agent_service.answer_customer_question.call_args
    assert call_args.args[2] == FAKE_ORDER
    update_payload = queries[3].update.call_args.args[0]
    assert update_payload["order_id"] == "order-1"
    assert update_payload["order_match_status"] == "matched"


def test_process_chat_message_never_raises_on_agent_failure():
    mock_supabase, queries = _make_supabase_mock(
        SimpleNamespace(data=None),
        SimpleNamespace(data=[_fake_inbound_row()]),
        SimpleNamespace(data=[]),
        SimpleNamespace(data=[_fake_inbound_row(ai_status="failed")]),
    )
    with (
        patch.object(inbound_service, "supabase", mock_supabase),
        patch.object(inbound_service, "agent_service") as mock_agent_service,
    ):
        mock_agent_service.answer_customer_question.side_effect = RuntimeError("Anthropic is down")
        result = inbound_service.process_chat_message("Do you deliver?", FAKE_CUSTOMER, None, "none")

    # Never raised, and the widget still gets a safe answer to show.
    assert result["answer"]
    update_payload = queries[3].update.call_args.args[0]
    assert update_payload == {"ai_status": "failed"}


# --- Chat-assisted ordering (process_order_assistant_message) --------------
# The agent_service.run_order_assistant_turn call itself is mocked at its
# exact boundary here (its own slot-collection/confirmation/order-creation
# logic is covered in test_agent_order_assistant.py) -- this is purely
# "did inbound_service wire the audit trail (record -> hand off -> update)
# the same way process_chat_message above already does."


def test_process_order_assistant_message_records_and_updates_the_inbound_row():
    mock_supabase, queries = _make_supabase_mock(
        SimpleNamespace(data=None),  # find existing: not found
        SimpleNamespace(data=[_fake_inbound_row(
            channel="email", provider_message_id="chat-order:whatever", sender_identifier="jane@example.com",
            subject="Chat order assistant", body="I'd like to order a cake",
        )]),  # insert
        SimpleNamespace(data=[_fake_inbound_row(
            customer_id="cust-1", order_id=None, ai_status="drafted", draft_notification_id="notif-1",
        )]),  # update
    )
    with (
        patch.object(inbound_service, "supabase", mock_supabase),
        patch.object(inbound_service, "agent_service") as mock_agent_service,
    ):
        mock_agent_service.run_order_assistant_turn.return_value = {
            "reply": "What size would you like?",
            "draft": {"templateId": "tpl-1", "cakeSizeId": None, "flavorId": None, "fillingId": None, "frostingId": None, "phone": None},
            "order_created": False,
            "order_id": None,
            "notification": {"id": "notif-1"},
            "ai_status": "drafted",
        }
        result = inbound_service.process_order_assistant_message("I'd like to order a cake", FAKE_CUSTOMER, {})

    inserted_payload = queries[1].insert.call_args.args[0]
    assert inserted_payload["channel"] == "email"  # not a new channel value, same as process_chat_message
    assert inserted_payload["provider_message_id"].startswith("chat-order:")

    update_payload = queries[2].update.call_args.args[0]
    assert update_payload["customer_id"] == "cust-1"
    assert update_payload["ai_status"] == "drafted"
    assert update_payload["draft_notification_id"] == "notif-1"

    assert result == {
        "reply": "What size would you like?",
        "draft": {"templateId": "tpl-1", "cakeSizeId": None, "flavorId": None, "fillingId": None, "frostingId": None, "phone": None},
        "orderCreated": False,
        "orderId": None,
    }
    mock_agent_service.run_order_assistant_turn.assert_called_once_with(
        "I'd like to order a cake", {}, FAKE_CUSTOMER, trigger_context=None
    )


def test_process_order_assistant_message_forwards_trigger_context():
    mock_supabase, _queries = _make_supabase_mock(
        SimpleNamespace(data=None),
        SimpleNamespace(data=[_fake_inbound_row()]),
        SimpleNamespace(data=[_fake_inbound_row(ai_status="drafted")]),
    )
    with (
        patch.object(inbound_service, "supabase", mock_supabase),
        patch.object(inbound_service, "agent_service") as mock_agent_service,
    ):
        mock_agent_service.run_order_assistant_turn.return_value = {
            "reply": "Got it!", "draft": {}, "order_created": False, "order_id": None,
            "notification": {"id": "notif-1"}, "ai_status": "drafted",
        }
        inbound_service.process_order_assistant_message(
            "chocolate, impressive", FAKE_CUSTOMER, {}, trigger_context="birthday cake for 20 nice people"
        )

    mock_agent_service.run_order_assistant_turn.assert_called_once_with(
        "chocolate, impressive", {}, FAKE_CUSTOMER, trigger_context="birthday cake for 20 nice people"
    )


def test_process_order_assistant_message_surfaces_order_id_when_created():
    mock_supabase, queries = _make_supabase_mock(
        SimpleNamespace(data=None),
        SimpleNamespace(data=[_fake_inbound_row()]),
        SimpleNamespace(data=[_fake_inbound_row(order_id="order-1", ai_status="drafted", draft_notification_id="notif-2")]),
    )
    with (
        patch.object(inbound_service, "supabase", mock_supabase),
        patch.object(inbound_service, "agent_service") as mock_agent_service,
    ):
        mock_agent_service.run_order_assistant_turn.return_value = {
            "reply": "Your order has been created — reference order-1.",
            "draft": {"templateId": None, "cakeSizeId": None, "flavorId": None, "fillingId": None, "frostingId": None, "phone": None},
            "order_created": True,
            "order_id": "order-1",
            "notification": {"id": "notif-2"},
            "ai_status": "drafted",
        }
        result = inbound_service.process_order_assistant_message("Yes, confirm", FAKE_CUSTOMER, {})

    assert result["orderCreated"] is True
    assert result["orderId"] == "order-1"
    update_payload = queries[2].update.call_args.args[0]
    assert update_payload["order_id"] == "order-1"


def test_process_order_assistant_message_never_raises_on_agent_failure():
    mock_supabase, queries = _make_supabase_mock(
        SimpleNamespace(data=None),
        SimpleNamespace(data=[_fake_inbound_row()]),
        SimpleNamespace(data=[_fake_inbound_row(ai_status="failed")]),
    )
    with (
        patch.object(inbound_service, "supabase", mock_supabase),
        patch.object(inbound_service, "agent_service") as mock_agent_service,
    ):
        mock_agent_service.run_order_assistant_turn.side_effect = RuntimeError("Anthropic is down")
        result = inbound_service.process_order_assistant_message("I'd like to order a cake", FAKE_CUSTOMER, {})

    assert result["reply"]
    assert result["orderCreated"] is False
    update_payload = queries[2].update.call_args.args[0]
    assert update_payload == {"customer_id": "cust-1", "ai_status": "failed"}


# --- Inbox / source-message lookups -----------------------------------------


def test_list_inbox_filters_to_rows_without_a_draft():
    query = _self_chaining_query_mock(SimpleNamespace(data=[_fake_inbound_row(ai_status="failed")]))
    with patch.object(inbound_service, "supabase") as mock_supabase:
        mock_supabase.table.return_value = query
        items = inbound_service.list_inbox()

    query.is_.assert_any_call("draft_notification_id", "null")
    assert len(items) == 1


def test_get_source_message_for_notification_returns_none_when_absent():
    query = _self_chaining_query_mock(SimpleNamespace(data=None))
    with patch.object(inbound_service, "supabase") as mock_supabase:
        mock_supabase.table.return_value = query
        result = inbound_service.get_source_message_for_notification("some-notification-id")

    assert result is None


def test_list_channel_messages_for_customer_filters_by_customer_and_channel():
    rows = [_fake_inbound_row(channel="whatsapp", body="Is my cake ready?")]
    query = _self_chaining_query_mock(SimpleNamespace(data=rows))
    with patch.object(inbound_service, "supabase") as mock_supabase:
        mock_supabase.table.return_value = query
        result = inbound_service.list_channel_messages_for_customer("cust-1", "whatsapp")

    query.eq.assert_any_call("customer_id", "cust-1")
    query.eq.assert_any_call("channel", "whatsapp")
    assert result == rows


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
