from datetime import date, datetime, time

from pydantic import BaseModel, Field


class OrderCreateRequest(BaseModel):
    template_id: str
    # Still required and still sent — see order_service.create_order's own
    # note on why it's only a fallback once guest_count is present, never
    # the customer-facing lever for price (Servings + Event Pricing).
    cake_size_id: str
    flavor_id: str
    filling_id: str
    frosting_id: str
    customer_name: str
    customer_phone: str
    customer_email: str
    notes: str | None = None
    # Required for every new order (Pickup Date + Order Priority, Phase 2)
    # -- Pydantic's own date/time parsing already rejects malformed values
    # with a clean 422, before this ever reaches order_service.
    # validate_pickup_datetime (the past/Monday/hours business rules
    # Pydantic can't know). Historical orders created before this field
    # existed keep NULL pickup_date/pickup_time — never backfilled.
    pickup_date: date
    pickup_time: time
    # Servings + Event Pricing: the primary business input driving size
    # and price (see order_service.create_order). gt=0 gives a clean 422
    # for zero/negative before this ever reaches the route's own 76+
    # eligibility check.
    guest_count: int = Field(gt=0)


class OrderCreateResponse(BaseModel):
    orderId: str


class OrderPublicView(BaseModel):
    """Minimal, unauthenticated, no-PII view of one order -- for the
    Website payment page and any other customer-facing surface that only
    has an order id (from a URL, a Chat/WhatsApp reply, etc.). Same
    unauthenticated posture as the rest of this router (no customer login
    exists in this project); deliberately omits customer name/email/phone,
    which nothing customer-facing needs to redisplay back at this point.
    """

    orderId: str
    templateName: str | None = None
    configuration: dict
    totalPrice: float
    orderStatus: str
    paymentStatus: str


class OrderPaymentResponse(BaseModel):
    """POST /orders/{id}/pay's response -- exactly what a customer needs
    to see (payment + resulting order status, the authoritative amount,
    the simulated reference), nothing about internal payment-row ids.
    """

    paymentStatus: str
    orderStatus: str
    amount: float
    simulatedReference: str | None = None
    paidAt: datetime | None = None
