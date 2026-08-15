"""Request/response schemas for admin order management
(`app/api/routes/admin/orders.py`).

Field names for the joined relations (`customers`, `cake_templates`) match
the PostgREST embedded-resource keys returned by
`app/services/order_service.py`'s `_ORDER_DETAIL_SELECT` exactly — same
convention as every other schema in this project (e.g. `CakeTemplateResponse`
mirrors `cake_templates` columns 1:1), so the service layer's raw dicts
validate against these models with no extra mapping step.
"""

from datetime import date, datetime, time

from pydantic import BaseModel


class AdminOrderPayment(BaseModel):
    """Simulated/demo payment status for the order detail drawer -- see
    app/services/payment_service.py's own docstring on why no real card
    data ever appears here (there is none, anywhere in this project).
    """

    status: str
    amount: float | None = None
    simulated_reference: str | None = None
    paid_at: datetime | None = None


class AdminOrderCustomer(BaseModel):
    id: str
    name: str
    email: str
    phone: str | None = None


class AdminOrderTemplate(BaseModel):
    id: str
    name: str
    category: str
    preview_image: str | None = None


class AdminOrderSummary(BaseModel):
    id: str
    status: str
    total_price: float
    created_at: datetime
    pickup_date: date | None = None
    pickup_time: time | None = None
    customers: AdminOrderCustomer | None = None
    cake_templates: AdminOrderTemplate | None = None


class AdminOrderDetail(AdminOrderSummary):
    notes: str | None = None
    configuration: dict
    payment: AdminOrderPayment | None = None


class AdminOrderListResponse(BaseModel):
    items: list[AdminOrderSummary]
    total: int
    page: int
    pageSize: int


class OrderStatusUpdateRequest(BaseModel):
    status: str


class OrderStatusUpdateResponse(AdminOrderDetail):
    """Same shape as AdminOrderDetail (the updated order) plus the id of
    the customer-update draft this transition created or reused, if the
    new status has a customer-facing template (see
    notification_templates.py -- every real status has one today). None
    only if drafting itself failed (create_notification_for_order_event
    never raises, see its own docstring -- a genuine failure there just
    means no draft, not a failed status update). Lets the drawer show
    "Customer update draft created" with a direct link into
    Communications right after the click that caused it, with no second
    round trip needed to find which notification it was.
    """

    notificationId: str | None = None
