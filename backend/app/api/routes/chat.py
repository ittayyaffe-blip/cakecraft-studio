"""Customer-facing website chat route — the landing page (and every
other customer-facing page) widget's two endpoints. No auth: same
unauthenticated posture as orders.py/designer.py/templates.py, since a
site visitor asking "is this gluten-free?" hasn't signed in and shouldn't
need to.

Reuses the existing AI Agent/RAG/inbound-communication architecture end
to end (see inbound_service.process_chat_message/process_order_assistant_
message and agent_service.answer_customer_question/run_order_assistant_
turn's own docstrings) — this route is glue, not a new pipeline:
identify-or-create the customer, hand off, return the result. /order is
the chat-assisted ordering MVP: still the same customer-identification
and inbound/notification persistence, still routed through the one
authoritative order_service.create_order() — nothing here builds a
second order-creation path.
"""

import logging

from fastapi import APIRouter, HTTPException

from app.schemas.chat import ChatAskRequest, ChatAskResponse, ChatOrderRequest, ChatOrderResponse
from app.services import inbound_service, order_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/ask", response_model=ChatAskResponse)
def ask(request: ChatAskRequest):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    try:
        customer_id = order_service.find_or_create_customer(request.name, None, request.email)
        # Derived server-side from the identified customer, never from
        # request.orderId -- see ChatAskRequest's own note on why.
        order, order_match_status = order_service.find_open_order_for_customer(customer_id)

        result = inbound_service.process_chat_message(
            question,
            {"id": customer_id, "name": request.name, "email": request.email},
            order,
            order_match_status,
        )
    except Exception:
        logger.exception("Chat ask failed for email=%s", request.email)
        raise HTTPException(status_code=500, detail="Failed to answer your question")

    return {"answer": result["answer"], "intent": result.get("intent")}


@router.post("/order", response_model=ChatOrderResponse)
def order(request: ChatOrderRequest):
    """One turn of chat-assisted ordering — the customer has already
    opted in (see ChatAskResponse.intent's own note; the widget only
    starts calling this once the customer clicks the "Start an order"
    nudge, never automatically). `draft` is whatever the previous turn's
    response returned (empty/absent on the very first turn); the AI only
    ever collects/updates it and asks for what's still missing — the
    actual order is created exactly once, only after the customer's own
    explicit confirmation, by the one existing order_service.create_order()
    (see agent_service.run_order_assistant_turn's own docstring for the
    full guardrail).
    """
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    try:
        customer_id = order_service.find_or_create_customer(request.name, None, request.email)
        result = inbound_service.process_order_assistant_message(
            message,
            {"id": customer_id, "name": request.name, "email": request.email},
            request.draft.model_dump() if request.draft else {},
        )
    except Exception:
        logger.exception("Chat order-assistant turn failed for email=%s", request.email)
        raise HTTPException(status_code=500, detail="Failed to process your message")

    return result
