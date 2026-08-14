"""Inbound Communication orchestration — Step 3 (+ the order form's Notes
field, wired in later — see process_order_note; + the website live-chat
widget, wired in later still — see process_chat_message).

Connects the inbound sources (communication.gmail_inbound,
communication.whatsapp_inbound, the order form's own Notes field, and the
website chat widget) to the existing AI Agent (agent_service.
draft_reply_to_inbound_message / answer_customer_question) and the
existing Notification Engine (those functions insert into `notifications`
exactly the way agent_service.draft_customer_communication already does
for staff-initiated drafts) — this module is glue, not a second pipeline:
it never talks to Claude, RAG, or a Communication Adapter directly.

Every inbound message is durably recorded in `inbound_messages` *before*
any customer/order matching or AI processing is attempted, and every
step after that updates the same row rather than risking the original
message — so a crash, an unknown sender, or an Anthropic API failure
never loses what the customer actually wrote (see the migration's own
docstring on why this is a separate table from `notifications`).

Idempotency: `inbound_messages` has a unique (channel, provider_message_id)
index (see the migration) — record_inbound_message() checks for an
existing row first and returns it unprocessed again rather than
inserting a duplicate, so a webhook retry or a re-run IMAP poll is safe.
"""

import logging
from datetime import datetime, timezone
from uuid import uuid4

from app.core.database import supabase
from app.services import agent_service, customer_service, order_service
from app.services.communication import gmail_inbound

logger = logging.getLogger(__name__)

_INBOUND_SELECT = "*, customers(id, name, email, phone)"


def _find_existing(channel: str, provider_message_id: str) -> dict | None:
    response = (
        supabase.table("inbound_messages")
        .select(_INBOUND_SELECT)
        .eq("channel", channel)
        .eq("provider_message_id", provider_message_id)
        .maybe_single()
        .execute()
    )
    return response.data if response is not None else None


def _record_inbound_message(
    *,
    channel: str,
    provider_message_id: str,
    sender_identifier: str,
    body: str,
    received_at: datetime,
    subject: str | None = None,
    thread_id: str | None = None,
) -> tuple[dict, bool]:
    """Idempotent insert: returns (row, is_new). A second call with the
    same (channel, provider_message_id) returns the existing row and
    False, never a duplicate — the one thing every caller (webhook
    retries, repeated IMAP polls) needs to be safe.
    """
    existing = _find_existing(channel, provider_message_id)
    if existing is not None:
        return existing, False

    payload = {
        "channel": channel,
        "provider_message_id": provider_message_id,
        "sender_identifier": sender_identifier,
        "subject": subject,
        "body": body,
        "received_at": received_at.isoformat(),
        "thread_id": thread_id,
    }
    try:
        response = supabase.table("inbound_messages").insert(payload).execute()
        return response.data[0], True
    except Exception:
        # A race: two near-simultaneous calls for the same message (e.g. a
        # webhook retry arriving before the first insert commits) could
        # both pass the _find_existing check above and both attempt an
        # insert — the unique index then rejects the second. Re-read
        # rather than raise, so the caller still gets a usable row instead
        # of an error for what is, semantically, not a real failure.
        logger.warning(
            "Insert raced or failed for channel=%s provider_message_id=%s; re-reading",
            channel,
            provider_message_id,
        )
        existing = _find_existing(channel, provider_message_id)
        if existing is not None:
            return existing, False
        raise


def _update_inbound_message(inbound_id: str, fields: dict) -> dict:
    response = supabase.table("inbound_messages").update(fields).eq("id", inbound_id).execute()
    return response.data[0]


def _identify_customer(channel: str, sender_identifier: str) -> tuple[dict | None, bool]:
    if channel == "email":
        return customer_service.find_customer_by_email(sender_identifier)
    if channel == "whatsapp":
        return customer_service.find_customer_by_phone(sender_identifier)
    return None, False


# Short-term context only, not a full case file — bounded so the prompt
# stays small and the AI Agent isn't reasoning over a customer's entire
# history for a single reply (see agent_service._format_conversation_
# history, which walls this off from the trusted-knowledge sections of
# the prompt and labels it explicitly as customer-authored, untrusted).
_CONVERSATION_HISTORY_LIMIT = 3


def get_recent_conversation(customer_id: str, *, before_created_at: str, limit: int = _CONVERSATION_HISTORY_LIMIT) -> list[dict]:
    """This customer's own most recent prior inbound messages, oldest
    first, excluding the one currently being processed — Step 3B's
    "what did they already say" context (see agent_service.
    draft_reply_to_inbound_message). Scoped to this one customer's own
    messages only, via the same customer_id every other query in this
    module already filters on — structurally incapable of pulling in
    another customer's conversation.
    """
    response = (
        supabase.table("inbound_messages")
        .select("body, received_at, created_at")
        .eq("customer_id", customer_id)
        .lt("created_at", before_created_at)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return list(reversed(response.data))


def list_channel_messages_for_customer(customer_id: str, channel: str) -> list[dict]:
    """Every inbound message from one customer on one channel, oldest
    first — the "incoming" half of a real conversation thread (see
    admin/communications.py's GET /whatsapp/thread/{customer_id}, which
    merges this with notification_service.list_notifications_for_
    customer's "outgoing" half). Unlike get_recent_conversation above
    (a capped, AI-prompt-sized window), this is unbounded — a human
    looking at their own conversation with a customer should see all of
    it, not a window sized for staying inside a Claude prompt.
    """
    response = (
        supabase.table("inbound_messages")
        .select("id, body, received_at")
        .eq("customer_id", customer_id)
        .eq("channel", channel)
        .order("received_at")
        .execute()
    )
    return response.data


def _draft_reply_and_update(inbound: dict, customer: dict, order: dict | None, order_match_status: str) -> dict:
    """Shared tail of inbound processing once a customer (and, where
    possible, an order) are already known: conversation context -> AI
    Agent -> update the inbound_messages row with whatever was learned.
    Used both by messages arriving through a real channel (customer/order
    resolved by lookup in _process_and_draft) and by an order-form note,
    where the customer and order are already known exactly, by
    construction (see process_order_note) — identical grounding,
    guardrails, and draft-only behavior either way, only how the
    customer/order were determined differs.

    Never raises: any unexpected failure here still leaves the *original*
    inbound message intact (already committed by _record_inbound_message
    before this is ever called) with ai_status left "failed" rather than
    losing the row or crashing the caller.
    """
    try:
        history = get_recent_conversation(customer["id"], before_created_at=inbound["created_at"])

        result = agent_service.draft_reply_to_inbound_message(
            inbound, customer, order, order_match_status=order_match_status, conversation_history=history
        )

        return _update_inbound_message(
            inbound["id"],
            {
                "customer_id": customer["id"],
                "order_id": order["id"] if order else None,
                "order_match_status": order_match_status,
                "ai_status": result["ai_status"],
                "draft_notification_id": result["notification"]["id"] if result["notification"] else None,
                "intent": result.get("intent"),
                "handling": result.get("handling"),
                "review_reason": result.get("review_reason"),
                "knowledge_sources": result.get("knowledge_sources"),
            },
        )
    except Exception:
        logger.exception("Failed to process inbound message %s", inbound.get("id"))
        try:
            return _update_inbound_message(inbound["id"], {"ai_status": "failed"})
        except Exception:
            logger.exception("Failed to even mark inbound message %s as failed", inbound.get("id"))
            return inbound


def _process_and_draft(inbound: dict) -> dict:
    """Customer identification -> order matching, then hand off to
    _draft_reply_and_update. Never raises: an identification/matching
    failure still leaves the *original* inbound message intact with
    ai_status left "failed", the same fail-open contract
    _draft_reply_and_update independently provides for the step after.
    """
    try:
        customer, _customer_ambiguous = _identify_customer(inbound["channel"], inbound["sender_identifier"])

        if customer is None:
            # Unknown (or ambiguous — see customer_service.find_customer_
            # by_email/_by_phone) sender: the message stays visible (see
            # GET /admin/communications/inbox) with no draft — the system
            # must not invent a customer identity, and a reply needs a
            # real customer_id (notifications.customer_id is not-null) to
            # become a draft at all.
            return _update_inbound_message(inbound["id"], {"ai_status": "failed"})

        order, order_match_status = order_service.find_open_order_for_customer(customer["id"])
    except Exception:
        logger.exception("Failed to identify customer/order for inbound message %s", inbound.get("id"))
        try:
            return _update_inbound_message(inbound["id"], {"ai_status": "failed"})
        except Exception:
            logger.exception("Failed to even mark inbound message %s as failed", inbound.get("id"))
            return inbound

    return _draft_reply_and_update(inbound, customer, order, order_match_status)


def process_order_note(order: dict, customer: dict) -> dict | None:
    """The order form's Notes field, treated as a real inbound customer
    message when it actually contains one — reuses the exact same
    inbound_messages record -> AI Agent -> draft pipeline every other
    channel already goes through (see module docstring). The only
    difference from a real inbound email: the customer and order are
    already known exactly, by construction (this note was submitted as
    part of creating this exact order), so there's no identify/match-
    order lookup to do — order_match_status is always "matched". Every
    other step (RAG retrieval, guardrails, intent/handling, human review,
    draft-only, idempotency) is identical to a real inbound email.

    `channel="email"` — not a new channel value: inbound_messages.channel
    has a real DB check constraint (`in ('email', 'whatsapp')`), and the
    customer's email address (required on every order) is exactly what a
    reply would go out through anyway, so this models the note as coming
    in via the channel a reply can actually be sent on, rather than
    inventing a third channel that no adapter is registered for.

    provider_message_id is deterministic (`order-note:<order_id>`), so
    the existing (channel, provider_message_id) unique index gives this
    the same idempotency guarantee every other inbound source already
    has — calling this twice for the same order is a safe no-op, not a
    duplicate draft.

    Returns None if the notes field is blank/whitespace-only — nothing
    to process, no row created, no AI call. Never raises: this runs
    inline with order creation and must never be able to break it (see
    the route's own try/except in app/api/routes/orders.py).
    """
    notes = (order.get("notes") or "").strip()
    if not notes:
        return None

    inbound, is_new = _record_inbound_message(
        channel="email",
        provider_message_id=f"order-note:{order['id']}",
        sender_identifier=customer["email"],
        subject="Message from order form",
        body=notes,
        received_at=datetime.now(timezone.utc),
    )
    if not is_new:
        logger.info("Order note for order=%s already recorded — skipping reprocessing", order["id"])
        return inbound

    return _draft_reply_and_update(inbound, customer, order, "matched")


def process_chat_message(question: str, customer: dict, order: dict | None, order_match_status: str) -> dict:
    """The website live-chat widget's entry point (api/routes/chat.py) —
    records the question in `inbound_messages` exactly like every other
    inbound source (same table, same audit trail for staff), but hands
    off to agent_service.answer_customer_question instead of
    draft_reply_to_inbound_message, and — unlike every other function in
    this module — returns the answer *text* synchronously, because the
    caller needs to show it to the customer right now, not just persist
    a row (see that function's own docstring for why this is the one
    exception to "AI never reaches a customer without human approval").

    `channel="email"` for the inbound_messages row — not a new channel
    value, same reasoning as process_order_note: the constraint only
    allows ('email', 'whatsapp'), and the customer's email (required to
    have an identity here at all — see order_service.find_or_create_
    customer) is exactly what a human-reviewed reply would go out
    through if this question needed escalation instead of a direct
    answer. `provider_message_id` is a fresh uuid per message, not a
    deterministic key like process_order_note's: one chat visitor can
    legitimately ask many separate questions, each its own row, not "the
    one note on this one order."

    Never raises: any unexpected failure still leaves the original
    inbound message intact (already committed before this is called)
    with ai_status left "failed", and still returns a safe, honest
    answer for the widget rather than letting the request fail.
    """
    inbound, _is_new = _record_inbound_message(
        channel="email",
        provider_message_id=f"chat:{uuid4()}",
        sender_identifier=customer["email"],
        subject="Website chat question",
        body=question,
        received_at=datetime.now(timezone.utc),
    )

    try:
        history = get_recent_conversation(customer["id"], before_created_at=inbound["created_at"])

        result = agent_service.answer_customer_question(
            question, customer, order, order_match_status=order_match_status, conversation_history=history
        )

        _update_inbound_message(
            inbound["id"],
            {
                "customer_id": customer["id"],
                "order_id": order["id"] if order else None,
                "order_match_status": order_match_status,
                "ai_status": result["ai_status"],
                "draft_notification_id": result["notification"]["id"] if result["notification"] else None,
                "intent": result.get("intent"),
                "handling": result.get("handling"),
                "review_reason": result.get("review_reason"),
                "knowledge_sources": result.get("knowledge_sources"),
            },
        )
        return {"answer": result["answer"], "intent": result.get("intent"), "handling": result.get("handling")}
    except Exception:
        logger.exception("Failed to process chat message for customer=%s", customer.get("id"))
        try:
            _update_inbound_message(inbound["id"], {"ai_status": "failed"})
        except Exception:
            logger.exception("Failed to even mark chat inbound message %s as failed", inbound.get("id"))
        return {
            "answer": "Sorry, I'm having trouble answering right now — please try again in a moment.",
            "intent": None,
            "handling": None,
        }


def process_order_assistant_message(
    message: str, customer: dict, draft: dict, *, trigger_context: str | None = None
) -> dict:
    """One turn of chat-assisted ordering (api/routes/chat.py's POST
    /order) — the same "record first, then hand off" contract as every
    other function in this module, and the same `inbound_messages` table/
    audit trail every other channel already uses (`channel="email"`, same
    reasoning as process_chat_message above: the DB constraint only
    allows `('email', 'whatsapp')`, and this customer's email is exactly
    what a human-reviewed follow-up would go out through if one were
    needed). All of the actual slot-collection/confirmation/order-
    creation logic lives in agent_service.run_order_assistant_turn — this
    function only wraps it with the same audit-trail bookkeeping
    process_chat_message already does, it never touches order_service or
    a Communication Adapter directly.

    `trigger_context` is passed straight through to run_order_assistant_
    turn unchanged — see that function's own docstring for exactly how
    (and how little) it's used.
    """
    inbound, _is_new = _record_inbound_message(
        channel="email",
        provider_message_id=f"chat-order:{uuid4()}",
        sender_identifier=customer["email"],
        subject="Chat order assistant",
        body=message,
        received_at=datetime.now(timezone.utc),
    )

    try:
        result = agent_service.run_order_assistant_turn(message, draft, customer, trigger_context=trigger_context)

        _update_inbound_message(
            inbound["id"],
            {
                "customer_id": customer["id"],
                "order_id": result.get("order_id"),
                "ai_status": result["ai_status"],
                "draft_notification_id": result["notification"]["id"] if result.get("notification") else None,
            },
        )
        return {
            "reply": result["reply"],
            "draft": result["draft"],
            "orderCreated": result["order_created"],
            "orderId": result["order_id"],
        }
    except Exception:
        logger.exception("Failed to process order-assistant message for customer=%s", customer.get("id"))
        try:
            _update_inbound_message(inbound["id"], {"customer_id": customer["id"], "ai_status": "failed"})
        except Exception:
            logger.exception("Failed to even mark order-assistant inbound message %s as failed", inbound.get("id"))
        return {
            "reply": "Sorry, I'm having trouble right now — please try again in a moment.",
            "draft": draft,
            "orderCreated": False,
            "orderId": None,
        }


def process_inbound_email(parsed: dict) -> dict:
    """Full pipeline for one parsed inbound email (see communication.
    gmail_inbound.parse_message / fetch_unread_messages) — record,
    identify, match order, hand to the AI Agent. The one place both the
    background poll and the manual "check now" trigger
    (app/api/routes/admin/communications.py) call into, so this logic
    exists exactly once.
    """
    message_id = parsed.get("message_id") or (
        f"no-message-id:{parsed['sender_email']}:{parsed['received_at'].isoformat()}"
    )
    inbound, is_new = _record_inbound_message(
        channel="email",
        provider_message_id=message_id,
        sender_identifier=parsed["sender_email"],
        subject=parsed.get("subject"),
        body=parsed["body"],
        received_at=parsed["received_at"],
        thread_id=parsed.get("thread_id"),
    )
    if not is_new:
        logger.info("Inbound email %s already recorded — skipping reprocessing", message_id)
        return inbound
    return _process_and_draft(inbound)


def process_inbound_whatsapp(parsed: dict) -> dict:
    """Same contract as process_inbound_email, for one parsed WhatsApp
    message (see communication.whatsapp_inbound.parse_webhook_payload).
    """
    timestamp_epoch = parsed.get("timestamp_epoch")
    received_at = (
        datetime.fromtimestamp(int(timestamp_epoch), tz=timezone.utc)
        if timestamp_epoch
        else datetime.now(timezone.utc)
    )

    inbound, is_new = _record_inbound_message(
        channel="whatsapp",
        provider_message_id=parsed["message_id"],
        sender_identifier=parsed["sender_phone"],
        body=parsed["body"],
        received_at=received_at,
    )
    if not is_new:
        logger.info("Inbound WhatsApp message %s already recorded — skipping reprocessing", parsed["message_id"])
        return inbound
    return _process_and_draft(inbound)


def check_for_new_email() -> list[dict]:
    """Manual/scheduled trigger: fetch + process every currently-unread
    inbound email in one pass (app/api/routes/admin/communications.py's
    POST /check-email, and main.py's background poll loop both call this
    same function). Returns the resulting inbound_messages rows.
    """
    if not gmail_inbound.is_configured():
        return []

    results = []
    for parsed in gmail_inbound.fetch_unread_messages():
        try:
            results.append(process_inbound_email(parsed))
        except Exception:
            logger.exception("Failed to process one inbound email during check_for_new_email")
    return results


def list_inbox(limit: int = 50) -> list[dict]:
    """Inbound messages that don't (yet) have a resulting draft —
    unknown/ambiguous sender, AI processing failure, or still pending —
    the Communications workspace's "Inbox" panel (see
    admin/communications.py). A message that *did* get a draft already
    shows up as that draft in the normal Communications list — this is
    deliberately not a second, parallel view of everything, only what
    still needs attention as a raw inbound message. Newest first, capped
    rather than paginated: this is meant to stay small in the common
    case (most messages do get drafted).
    """
    response = (
        supabase.table("inbound_messages")
        .select(_INBOUND_SELECT)
        .is_("draft_notification_id", "null")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return response.data


def get_source_message_for_notification(notification_id: str) -> dict | None:
    """The inbound message a given draft notification was created from,
    if any — the Communications drawer's "Customer message" section (see
    admin/notifications.py's GET /{id}/source-message) uses this to show
    the original message above the AI's draft reply. None for every
    notification created by the *other* paths (an order-status change,
    or a staff-initiated on-demand draft) — most notifications, not an
    error case.
    """
    response = (
        supabase.table("inbound_messages")
        .select(_INBOUND_SELECT)
        .eq("draft_notification_id", notification_id)
        .maybe_single()
        .execute()
    )
    return response.data if response is not None else None
