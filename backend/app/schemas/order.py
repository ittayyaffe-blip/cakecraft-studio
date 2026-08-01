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
