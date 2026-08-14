from datetime import datetime

from pydantic import BaseModel


class OrderCreateRequest(BaseModel):
    template_id: str
    cake_size_id: str
    flavor_id: str
    filling_id: str
    frosting_id: str
    customer_name: str
    customer_phone: str
    customer_email: str
    notes: str | None = None


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
