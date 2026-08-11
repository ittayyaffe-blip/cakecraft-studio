"""Event-driven, channel-agnostic notification service.

See docs/SPRINT1_EVENT_DRIVEN_COMMUNICATION.md for the full design. In one
paragraph: an order-status change creates a `notifications` row, a
deterministic template renders its content, and it sits in a queue where a
human must submit, approve, and finally send it. `send()` is the one
function a real channel adapter plugs into (see its docstring and
docs/SPRINT3_COMMUNICATION_ADAPTER.md) — as of Sprint 3, a Gmail adapter
is the first one actually wired in (app/services/communication/).

Status lifecycle (matches the `notifications.status` check constraint):

    queued -> draft -> awaiting_approval -> approved -> sent / failed
                 ^_____________|_______________|___________|
                  (return_to_draft, from any of these three)

`delivered` is still reserved for a future real channel adapter with an
async delivery-confirmation webhook (Gmail/SMTP's success already *is*
synchronous delivery-to-provider, so `send()` never sets it) — nothing in
this project sets it yet. `failed` is real as of this sprint: see
`_dispatch()`.
"""

import logging
from datetime import datetime, timezone

from app.core.database import supabase
from app.services import communication, notification_templates
from app.services.communication.base import DeliveryResult

logger = logging.getLogger(__name__)

NOTIFICATION_STATUSES = (
    "queued",
    "draft",
    "awaiting_approval",
    "approved",
    "sent",
    "delivered",  # reserved — no code path sets this yet
    "failed",  # reserved — no code path sets this yet
)

# Communications Workspace (Step 2) — the coarse "what needs my attention"
# grouping the admin route's `view` param maps to. `failed` belongs here,
# not with "sent": a failed send needs a human to fix and resubmit it, the
# same kind of action item as an unsubmitted draft, not a delivered outcome.
NEEDS_REVIEW_STATUSES = ("draft", "awaiting_approval", "failed")

# Where a notification's content originated — derived from the existing
# `event` field, not a new column: "agent_drafted" is the one event key
# the AI Agent's on-demand draft path uses (see agent_service.py); every
# other event key comes from an order-status transition's deterministic
# template (notification_templates.py), i.e. "automated".
VALID_SOURCES = ("automated", "ai_drafted")

# Step 3B: also embeds the linked order's cake/status/pickup-date (via a
# nested PostgREST embed, orders -> cake_templates) so the Communications
# drawer can show "Order context" (see admin_notification.py's
# AdminNotificationOrder) — a read-time join, not a new column/migration.
# order_id is nullable (an AI-drafted reply to a general question may
# have none — see the Step 3 migration), so this embeds as null too.
#
# `inbound_messages(...)` is a *reverse* embed (inbound_messages.
# draft_notification_id references notifications.id) — PostgREST returns
# it as a list even though at most one inbound message ever links to a
# given draft by construction; the Communications list/drawer take the
# first (only) entry when present. Empty for every notification created
# by the other two paths (an order-status change, or a staff-initiated
# on-demand draft) — most notifications, not an error.
_NOTIFICATION_SELECT = (
    "*, customers(id, name, email, phone), orders(id, status, pickup_date, cake_templates(name, category)), "
    "inbound_messages(intent, handling, review_reason, knowledge_sources)"
)


def _page_to_range(page: int, page_size: int) -> tuple[int, int]:
    """Same conversion as order_service._page_to_range / customer_service's
    copy of it — 1-based page/size to the 0-based, inclusive (start, end)
    range `.range()` expects. See those modules for why this stays a
    local, tiny duplicate rather than a shared import (no shared state,
    two lines of arithmetic).
    """
    start = (page - 1) * page_size
    end = start + page_size - 1
    return start, end


def get_event_label(event_key: str) -> str:
    """Human-readable label for an event key, e.g. for the Customer
    Timeline (customer_service.get_customer_timeline)."""
    return notification_templates.EVENT_LABELS.get(event_key, event_key)


def _insert_queued(order: dict, event_key: str, *, created_at: str | None = None) -> dict:
    payload = {
        "order_id": order["id"],
        "customer_id": order["customer_id"],
        "event": event_key,
        "status": "queued",
        # Default to "email" from creation, same as agent_service.
        # draft_customer_communication already does for AI drafts — a
        # notification's intended channel should be knowable the moment
        # it exists, not only once it's actually sent (_dispatch() would
        # otherwise resolve a null channel to DEFAULT_CHANNEL at send
        # time regardless, so this makes the visible value match the
        # real one, it doesn't change dispatch behavior).
        "channel": "email",
    }
    if created_at is not None:
        payload["created_at"] = created_at
    response = supabase.table("notifications").insert(payload).execute()
    return response.data[0]


def _render_draft(notification: dict, template: dict, order: dict) -> dict:
    rendered = notification_templates.render(template, order)
    response = (
        supabase.table("notifications")
        .update({"status": "draft", "subject": rendered["subject"], "body": rendered["body"]})
        .eq("id", notification["id"])
        .execute()
    )
    return response.data[0]


def _find_existing_event_notification(order_id: str, event_key: str) -> dict | None:
    """Idempotency check: has a notification for this exact (order, event)
    pair already been created? Same pattern inbound_service._find_existing
    already uses for inbound-message dedup — a plain query-before-insert,
    no schema change, since `order_id`/`event` are already real columns.
    """
    response = (
        supabase.table("notifications")
        .select(_NOTIFICATION_SELECT)
        .eq("order_id", order_id)
        .eq("event", event_key)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def create_notification_for_order_event(
    order: dict, order_status: str, *, created_at: str | None = None
) -> dict | None:
    """Create (and immediately render) a notification for one order-status
    transition, or return the existing one / None — see below — if there's
    nothing new to create. Not every transition is customer-relevant (see
    notification_templates.py).

    Called from app/api/routes/admin/orders.py's status-update route right
    after the order status itself is updated and audited, and from
    app/api/routes/orders.py's order-creation route for the initial
    `pending` -> "order received" event — the same function, two call
    sites, no separate creation path for "the first event" vs. "every
    later one."

    Idempotent per (order_id, event): re-processing the same transition —
    a staff member re-saving the same status, a retried request, a
    duplicate webhook-style call — returns the *existing* notification
    instead of inserting a second one. This is an application-level check
    (not a DB constraint) matching this function's existing "fail safe,
    never block the caller" contract; a concurrent-request race remains
    theoretically possible, same class of gap this project accepts
    elsewhere at this scale (see customer_service.find_customer_by_email's
    own docstring on a comparable tradeoff).

    `created_at` is a keyword-only override used exclusively by
    tools/demo_data_seed.py to backdate a seeded notification to when that
    status transition "happened" historically (see
    docs/SPRINT2_DEMO_DATA.md). The real call sites never pass it, so
    notifications keep their normal DB-generated `now()` value exactly as
    before this parameter existed.

    Never raises: a failure here must not block the order-status update
    (or order creation) it's reacting to — the same fail-open philosophy
    audit_service.record_event already established. "No template for this
    status," "already created," and "creation failed unexpectedly" all
    return without raising; callers don't need to tell them apart.
    """
    template = notification_templates.get_template_for_status(order_status)
    if template is None:
        return None

    try:
        existing = _find_existing_event_notification(order["id"], template["event"])
        if existing is not None:
            logger.info(
                "Notification for order=%s event=%s already exists (id=%s) — skipping duplicate",
                order["id"], template["event"], existing["id"],
            )
            return existing

        queued = _insert_queued(order, template["event"], created_at=created_at)
        return _render_draft(queued, template, order)
    except Exception:
        logger.exception(
            "Failed to create notification for order=%s status=%s", order["id"], order_status
        )
        return None


def list_notifications(
    status: str | None = None,
    statuses: tuple[str, ...] | None = None,
    channel: str | None = None,
    source: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Search/paginate the notification queue for the admin screen —
    the Communications Workspace (Step 2) filters on top of it.

    `status` (single exact match) is the original Sprint 1 filter,
    unchanged and still available. `statuses` (Communications Workspace's
    `view` param — see admin/notifications.py) is a coarse OR-of-statuses
    grouping, e.g. NEEDS_REVIEW_STATUSES; it takes priority over `status`
    if both are somehow given, since one route only ever passes one or
    the other. `channel`/`source` are new, independent filters — `source`
    is derived from the existing `event` field (see VALID_SOURCES), not a
    new column.
    """
    query = supabase.table("notifications").select(_NOTIFICATION_SELECT, count="exact")

    if statuses:
        query = query.in_("status", list(statuses))
    elif status:
        query = query.eq("status", status)

    if channel:
        query = query.eq("channel", channel)

    if source == "ai_drafted":
        query = query.eq("event", "agent_drafted")
    elif source == "automated":
        query = query.neq("event", "agent_drafted")

    start, end = _page_to_range(page, page_size)
    response = query.order("created_at", desc=True).range(start, end).execute()

    return {
        "items": response.data,
        "total": response.count or 0,
        "page": page,
        "pageSize": page_size,
    }


def list_notifications_for_customer(customer_id: str) -> list[dict]:
    """Every notification for one customer, newest first — unpaginated,
    matching order_service.get_orders_for_customer's shape. Used by
    customer_service.get_customer_timeline to fold notification events
    into the same unified feed order-placed/status-changed events already
    populate.
    """
    response = (
        supabase.table("notifications")
        .select(_NOTIFICATION_SELECT)
        .eq("customer_id", customer_id)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data


def get_notification_by_id(notification_id: str) -> dict | None:
    response = (
        supabase.table("notifications")
        .select(_NOTIFICATION_SELECT)
        .eq("id", notification_id)
        .maybe_single()
        .execute()
    )
    return response.data if response is not None else None


def update_draft_content(notification: dict, subject: str, body: str) -> dict:
    """Edit a notification's rendered content. Raises ValueError unless
    it's currently in `draft` — once submitted, use return_to_draft to get
    back here first rather than editing an in-flight approval.
    """
    if notification["status"] != "draft":
        raise ValueError(f"Cannot edit notification in status '{notification['status']}'")

    supabase.table("notifications").update({"subject": subject, "body": body}).eq(
        "id", notification["id"]
    ).execute()
    return get_notification_by_id(notification["id"])


def _transition(
    notification: dict, allowed_from: tuple[str, ...], to_status: str, extra: dict | None = None
) -> dict:
    """Guarded status transition, shared by every action below.

    `notification` is the caller's already-fetched row — the route fetches
    it once for its own 404 check (see admin/notifications.py), exactly
    like admin/orders.py's status route does for orders — so this function
    only re-validates the *current* status, not existence.
    """
    if notification["status"] not in allowed_from:
        raise ValueError(
            f"Cannot move notification from '{notification['status']}' to '{to_status}'"
        )

    update = {"status": to_status, **(extra or {})}
    supabase.table("notifications").update(update).eq("id", notification["id"]).execute()
    return get_notification_by_id(notification["id"])


def submit_for_approval(notification: dict) -> dict:
    """draft -> awaiting_approval. Any active staff member."""
    return _transition(notification, ("draft",), "awaiting_approval")


def approve(notification: dict) -> dict:
    """awaiting_approval -> approved. Restricted to the `admin` role at
    the route layer (require_role("admin")) — this function itself only
    enforces the status guard; role enforcement belongs to the route,
    matching how every other authorization check in this project works.
    """
    return _transition(notification, ("awaiting_approval",), "approved")


# A named constant (not an inline tuple) specifically so
# tests/test_communication_adapters.py can assert "failed" is included
# without needing to call return_to_draft itself, which would reach a
# real Supabase update — see that test for why that matters right now.
_RETURN_TO_DRAFT_ALLOWED_FROM = ("awaiting_approval", "approved", "failed")


def return_to_draft(notification: dict) -> dict:
    """awaiting_approval, approved, or failed -> draft — a human decided
    it needs more work (or a failed send needs a fix and a retry). Not
    part of Sprint 1's originally suggested status list, but a real
    approval workflow with no way back from a mistake — or a real delivery
    failure — would be an operational dead end; this is the minimal
    addition that avoids both without introducing a new status value.
    `failed` was added to this guard in Sprint 3, alongside `send()`
    actually being able to produce it for the first time.
    """
    return _transition(notification, _RETURN_TO_DRAFT_ALLOWED_FROM, "draft")


def _dispatch(notification: dict) -> tuple[str, DeliveryResult]:
    """Resolve this notification's channel to a registered adapter and
    attempt real delivery — the one place send() below touches the
    Communication Adapter layer (app/services/communication/).

    Falls back to the original Sprint 1 stub (report success, nothing
    actually delivered) in two distinct cases, both treated identically:
    no adapter is registered for this channel at all, OR one is
    registered but reports itself unconfigured (no real credentials —
    see e.g. gmail_adapter.is_configured()). That second case matters:
    Gmail is registered in every environment (see
    app/services/communication/__init__.py), but has no real credentials
    configured anywhere yet, including where tools/demo_data_seed.py
    will eventually run — this is what keeps that seeder's simulated
    "sent" notifications realistic without a real Gmail account, and
    keeps this whole engine's behavior identical to before this sprint
    everywhere Gmail credentials simply haven't been set up.
    """
    channel = notification.get("channel") or communication.DEFAULT_CHANNEL
    adapter = communication.get_adapter(channel)

    if adapter is None or not adapter.is_configured():
        return channel, DeliveryResult(success=True)

    return channel, adapter.send(notification)


def send(notification: dict, *, sent_at: str | None = None) -> dict:
    """approved -> sent, or approved -> failed if a configured adapter's
    real delivery attempt fails (see _dispatch()). This is the channel-
    agnostic dispatch surface Sprint 1 designed: a real channel adapter
    (Gmail, wired in this sprint; WhatsApp next) plugs into _dispatch()
    via the Communication Adapter registry, and neither the queue,
    drafting, nor approval steps above needed to change for that to
    happen.

    `sent_at` is a keyword-only override used exclusively by
    tools/demo_data_seed.py to backdate a seeded notification's send time
    to a believable historical moment rather than "now" (see
    docs/SPRINT2_DEMO_DATA.md). The real call site (the /send route) never
    passes it, so sent_at keeps recording the real current time exactly as
    before this parameter existed.
    """
    if notification["status"] != "approved":
        raise ValueError(f"Cannot move notification from '{notification['status']}' to 'sent'")

    channel, result = _dispatch(notification)

    if result.success:
        resolved_sent_at = sent_at or datetime.now(timezone.utc).isoformat()
        return _transition(
            notification,
            ("approved",),
            "sent",
            extra={
                "sent_at": resolved_sent_at,
                "channel": channel,
                "provider_message_id": result.provider_message_id,
            },
        )

    return _transition(notification, ("approved",), "failed", extra={"channel": channel})
