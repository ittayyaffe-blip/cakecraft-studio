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

from datetime import datetime

from pydantic import BaseModel

from app.schemas.admin_order import AdminOrderCustomer as NotificationCustomer


class AdminNotification(BaseModel):
    id: str
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
    customers: NotificationCustomer | None = None


class AdminNotificationListResponse(BaseModel):
    items: list[AdminNotification]
    total: int
    page: int
    pageSize: int


class NotificationContentUpdateRequest(BaseModel):
    subject: str
    body: str
