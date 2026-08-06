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


class AdminOrderListResponse(BaseModel):
    items: list[AdminOrderSummary]
    total: int
    page: int
    pageSize: int


class OrderStatusUpdateRequest(BaseModel):
    status: str
