import logging

from fastapi import APIRouter, HTTPException

from app.schemas.order import OrderCreateRequest, OrderCreateResponse
from app.services import inbound_service, notification_service, order_service
from app.services.order_service import create_order

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("", response_model=OrderCreateResponse)
def create_order_route(order: OrderCreateRequest):
    try:
        order_id = create_order(order.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Failed to create order")
        raise HTTPException(status_code=500, detail="Failed to create order")

    if order_id is None:
        raise HTTPException(status_code=404, detail="Cake template not found")

    # Step 5 — Event-Driven Customer Communication Platform: the same
    # draft-a-notification step admin/orders.py's status-update route
    # already does for every later transition, now also covering the
    # very first one. Fetched fresh (not built from the raw `order` input)
    # so it carries the joined customer/template shape
    # notification_templates.render() expects — mirrors how the
    # status-update route already gets a fully-joined order back from
    # order_service.update_order_status(). Never blocks order creation:
    # create_notification_for_order_event() never raises, and its result
    # is intentionally unused here, same as the status-update route.
    created_order = None
    try:
        created_order = order_service.get_order_by_id(order_id)
        if created_order is not None:
            notification_service.create_notification_for_order_event(created_order, "pending")
    except Exception:
        logger.exception("Failed to draft the order-received notification for order=%s", order_id)

    # A customer question typed into the order form's Notes field is a
    # real inbound message, not just an internal annotation for staff —
    # route it through the exact same inbound -> RAG -> AI Agent -> draft
    # pipeline Email/WhatsApp already use (see inbound_service.
    # process_order_note, which itself no-ops on a blank notes field).
    # Same fail-open contract as the notification hook above: never blocks
    # order creation.
    try:
        if created_order is not None and created_order.get("customers"):
            inbound_service.process_order_note(created_order, created_order["customers"])
    except Exception:
        logger.exception("Failed to process order-note inbound message for order=%s", order_id)

    return {"orderId": order_id}
