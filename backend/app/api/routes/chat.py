"""Customer-facing website chat route — the landing page (and every
other customer-facing page) widget's one endpoint. No auth: same
unauthenticated posture as orders.py/designer.py/templates.py, since a
site visitor asking "is this gluten-free?" hasn't signed in and shouldn't
need to.

Reuses the existing AI Agent/RAG/inbound-communication architecture end
to end (see inbound_service.process_chat_message and agent_service.
answer_customer_question's own docstrings) — this route is glue, not a
new pipeline: identify-or-create the customer, find their order (if any),
hand off, return the answer.
"""

import logging

from fastapi import APIRouter, HTTPException

from app.schemas.chat import ChatAskRequest, ChatAskResponse
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

    return {"answer": result["answer"]}
