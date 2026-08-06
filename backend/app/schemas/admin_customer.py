"""Request/response schemas for the Customers screen
(`app/api/routes/admin/customers.py`) — Epic 1.2, Customer Management & CRM.

`id`/`name`/`email`/`phone`/`created_at` mirror the `customers` table's own
columns 1:1 (same convention as `AdminOrderSummary` for `orders`).
`orderCount`/`lifetimeValue`/`lastOrderDate` are computed, not raw columns,
so — matching the camelCase-for-computed-fields convention already used in
`admin_dashboard.py` (`totalOrders`, `todaysOrders`) and pagination fields
(`pageSize`) — they're camelCase rather than snake_case.

Order history reuses `AdminOrderSummary` directly rather than a parallel
schema: a customer's order history is a list of real orders, in the exact
shape the Orders screen already returns them.
"""

from datetime import datetime

from pydantic import BaseModel


class AdminCustomerSummary(BaseModel):
    id: str
    name: str
    email: str
    phone: str | None = None
    created_at: datetime
    orderCount: int
    lifetimeValue: float
    lastOrderDate: datetime | None = None


class AdminCustomerDetail(AdminCustomerSummary):
    """Same fields as the list row today — kept as its own model (rather
    than reusing AdminCustomerSummary directly as the response_model)
    because the profile screen is expected to grow fields the list row
    never needs (e.g. internal notes/tags, per
    Bakery_Command_Center_UX_Product_Blueprint_v1.md §6's 'future' list),
    without that growth changing the list endpoint's response shape.
    """


class CustomerTimelineEvent(BaseModel):
    """One entry in a customer's timeline. Deliberately one flexible shape
    for every event type rather than a union of event-specific models —
    `type` tells the frontend which of the optional fields are populated
    (see customer_service.get_customer_timeline for the three kinds
    emitted today: "order_placed", "order.status_changed", and
    "notification" — the last added by the Event-Driven Customer
    Communication Platform sprint, using the `label`/`notificationId`
    fields added alongside it below). A future real-channel-delivery event
    is expected to slot into this same shape too, once Communications
    ships (Master_Blueprint_v1.md §10) — that's the "without refactoring"
    this schema was designed for from the start.
    """

    type: str
    timestamp: datetime
    orderId: str | None = None
    templateName: str | None = None
    status: str | None = None
    before: dict | None = None
    after: dict | None = None
    actorName: str | None = None
    label: str | None = None
    notificationId: str | None = None


class CustomerCommunicationsResponse(BaseModel):
    """Always `enabled: False, items: []` until Master_Blueprint_v1.md §10
    (Gmail/WhatsApp) ships — see customer_service.get_customer_communications.
    `items` is untyped (`list[dict]`) on purpose: its real shape
    (channel/recipient/preview/status/sentAt) is already specified in
    Bakery_Command_Center_UX_Product_Blueprint_v1.md §8 but committing to a
    strict schema for data that doesn't exist yet would be guessing ahead
    of that phase's real design work.
    """

    enabled: bool
    items: list[dict] = []


class CustomerAIInsightsResponse(BaseModel):
    """Always `enabled: False, insights: []` until the AI layer
    (Master_Blueprint_v1.md §9) ships — see
    customer_service.get_customer_ai_insights. Same reasoning as
    CustomerCommunicationsResponse for leaving `insights` untyped for now.
    """

    enabled: bool
    insights: list[dict] = []


class AdminCustomerListResponse(BaseModel):
    items: list[AdminCustomerSummary]
    total: int
    page: int
    pageSize: int
