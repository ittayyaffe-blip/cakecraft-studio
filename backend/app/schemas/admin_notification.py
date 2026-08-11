"""Request/response schemas for the Notification Queue screen
(`app/api/routes/admin/notifications.py`) — Event-Driven Customer
Communication Platform.

`customers` mirrors the PostgREST embedded-resource key returned by
`notification_service._NOTIFICATION_SELECT` (`customers(id, name, email,
phone)`) — the exact same lean embed shape `admin_order.py`'s
`AdminOrderCustomer` already models for orders, so it's reused directly
rather than duplicated. (`admin_customer.py`'s `AdminCustomerSummary`
would NOT work here: it requires `created_at`/`orderCount`/etc., none of
which this embed selects.)

One flat model (`AdminNotification`) serves both the list and detail
views — unlike Orders/Customers, nothing here needs extra fields only the
detail view shows, so a second model would just duplicate this one.
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.admin_order import AdminOrderCustomer as NotificationCustomer


class AdminNotificationTemplate(BaseModel):
    name: str
    category: str


class AdminNotificationOrder(BaseModel):
    """Step 3B — "Order context" in the Communications drawer: the
    minimum fields a reviewer needs (which cake, current status, when
    it's due), not the full order record. Nullable/absent whenever
    `order_id` is null (see notification_service._NOTIFICATION_SELECT).
    """

    id: str
    status: str
    pickup_date: date | None = None
    cake_templates: AdminNotificationTemplate | None = None


class AdminNotificationIntelligence(BaseModel):
    """Step 3B's intent/handling/review-reason/knowledge-sources — read
    via a reverse embed from the originating inbound_messages row (see
    notification_service._NOTIFICATION_SELECT); absent for every
    notification not created from an inbound message.
    """

    intent: str | None = None
    handling: str | None = None
    review_reason: str | None = None
    knowledge_sources: list[dict[str, Any]] | None = None


class AdminNotification(BaseModel):
    id: str
    # Nullable as of Step 3 (Inbound Communication -> AI Agent + RAG):
    # every pre-existing creation path always has a real order, but an
    # AI-drafted reply to an inbound message may not (see
    # supabase/migrations/20260810090000_create_inbound_messages.sql) —
    # a prospective/general customer question has no order to attach to.
    order_id: str | None = None
    customer_id: str
    event: str
    channel: str | None = None
    status: str
    subject: str | None = None
    body: str | None = None
    provider_message_id: str | None = None
    sent_at: datetime | None = None
    created_at: datetime
    # Not a DB column -- only ever set (by notification_service.send()) on
    # the direct response to a /send call that just failed, so the admin
    # sees exactly why immediately. Absent on every other response,
    # including a later GET of this same notification.
    error: str | None = None
    customers: NotificationCustomer | None = None
    orders: AdminNotificationOrder | None = None
    # A reverse embed always returns a list (see _NOTIFICATION_SELECT's
    # own note on why) — at most one entry by construction; the route
    # layer never needs to unwrap it, the frontend takes the first entry.
    inbound_messages: list[AdminNotificationIntelligence] = []


class AdminNotificationListResponse(BaseModel):
    items: list[AdminNotification]
    total: int
    page: int
    pageSize: int


class NotificationContentUpdateRequest(BaseModel):
    subject: str
    body: str
