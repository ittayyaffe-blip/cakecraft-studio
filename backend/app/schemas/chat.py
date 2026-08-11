"""Request/response schema for the customer-facing website chat widget
(app/api/routes/chat.py).
"""

from pydantic import BaseModel


class ChatAskRequest(BaseModel):
    name: str
    email: str
    question: str
    # Purely a hint for the frontend's own convenience -- the route never
    # trusts this for grounding: which order (if any) is used comes from
    # order_service.find_open_order_for_customer, derived server-side from
    # the identified customer, so a client can never point the AI at
    # someone else's order by passing an arbitrary id here.
    orderId: str | None = None


class ChatAskResponse(BaseModel):
    answer: str
