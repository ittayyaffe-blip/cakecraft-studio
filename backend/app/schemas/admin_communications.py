"""Request/response schemas for Step 3's inbound-communication endpoints
(app/api/routes/admin/communications.py, plus the `/source-message`
addition to app/api/routes/admin/notifications.py).

`customers` mirrors the same lean embedded shape `admin_notification.py`'s
`AdminNotification` already reuses from `admin_order.py` — see that
file's own docstring for why a third copy isn't worth it.

`intent`/`handling`/`review_reason`/`knowledge_sources` are Step 3B's
communication-intelligence fields (see supabase/migrations/
20260811090000_add_inbound_message_intelligence.sql and
agent_service.draft_reply_to_inbound_message) — all nullable since rows
created before Step 3B have none of them.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.admin_order import AdminOrderCustomer as InboundMessageCustomer


class AdminInboundMessage(BaseModel):
    id: str
    customer_id: str | None = None
    order_id: str | None = None
    order_match_status: str
    channel: str
    provider_message_id: str
    thread_id: str | None = None
    sender_identifier: str
    subject: str | None = None
    body: str
    received_at: datetime
    ai_status: str
    draft_notification_id: str | None = None
    intent: str | None = None
    handling: str | None = None
    review_reason: str | None = None
    knowledge_sources: list[dict[str, Any]] | None = None
    created_at: datetime
    customers: InboundMessageCustomer | None = None


class AdminInboxResponse(BaseModel):
    items: list[AdminInboundMessage]


class CheckEmailResponse(BaseModel):
    checked: int
    items: list[AdminInboundMessage]


class WhatsAppStatusResponse(BaseModel):
    """See app.services.communication.whatsapp_status — `provider` is
    `"twilio_sandbox"`, `"meta"`, or `None`; `sandboxNumber` is only ever
    set alongside `"twilio_sandbox"`, and is Twilio's own publicly
    documented shared Sandbox number, never a secret.
    """

    configured: bool
    provider: str | None = None
    sandboxNumber: str | None = None


class WhatsAppThreadMessage(BaseModel):
    """One message in a customer's WhatsApp thread (GET /whatsapp/thread/
    {customer_id}) — a merged, chronological view over the two existing
    tables this project already has (inbound_messages for "incoming",
    notifications for "outgoing"), not a new message-store. `status` is
    only ever set for an outgoing message (a real notifications.status —
    draft/sent/failed/etc.); an incoming message has none, it simply
    arrived.
    """

    direction: str  # "incoming" | "outgoing"
    body: str
    subject: str | None = None
    timestamp: datetime
    status: str | None = None


class WhatsAppThreadResponse(BaseModel):
    customer: InboundMessageCustomer | None = None
    messages: list[WhatsAppThreadMessage]


class WhatsAppReplyRequest(BaseModel):
    customerId: str
    body: str
