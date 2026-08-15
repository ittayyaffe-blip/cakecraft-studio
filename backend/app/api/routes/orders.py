import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.schemas.order import (
    OrderCreateRequest,
    OrderCreateResponse,
    OrderPaymentResponse,
    OrderPublicView,
)
from app.services import inbound_service, notification_service, order_service, payment_service
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


@router.get("/{order_id}", response_model=OrderPublicView)
def get_order_route(order_id: uuid.UUID):
    """Minimal, unauthenticated order view -- same unauthenticated posture
    as every other route in this file (see OrderPublicView's own note).
    Backs the Website payment page and any other surface that only has an
    order id; never returns customer PII.
    """
    order_id_str = str(order_id)
    order = order_service.get_order_by_id(order_id_str)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    payment = payment_service.get_payment_for_order(order_id_str)
    template = order.get("cake_templates") or {}
    return {
        "orderId": order["id"],
        "templateName": template.get("name"),
        "configuration": order.get("configuration") or {},
        "totalPrice": order["total_price"],
        "orderStatus": order["status"],
        "paymentStatus": payment["status"] if payment else "pending",
    }


@router.post("/{order_id}/pay", response_model=OrderPaymentResponse)
def pay_order_route(order_id: uuid.UUID, background_tasks: BackgroundTasks):
    """Simulated/demo payment -- see payment_service.simulate_payment's
    own docstring for the full idempotency/authoritative-amount contract
    and for exactly what the synchronous critical path is (order
    payable, payment marked paid, order confirmed, idempotency -- that's
    it). The ONE endpoint Website, Chat, and WhatsApp all call; no
    amount is ever accepted here -- it's always orders.total_price.

    Drafting the confirmed-order notification is NOT on the critical
    path: nobody is waiting on it for a successful payment response (a
    human still reviews/sends it later, exactly as before -- this only
    changes when the draft gets created, not the human-in-the-loop send
    step). Scheduled as a FastAPI BackgroundTask -- an existing
    Starlette/FastAPI feature, not new infrastructure -- so it runs
    after the response is already on its way to the customer.
    payment_service only ever returns a non-None "notification_order"
    on the one call that actually performs the transition, so a retry
    or an idempotent already-paid call never schedules a duplicate.
    """
    order_id_str = str(order_id)
    try:
        result = payment_service.simulate_payment(order_id_str)
    except payment_service.OrderNotFoundError:
        raise HTTPException(status_code=404, detail="Order not found")
    except payment_service.OrderNotPayableError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Failed to process payment for order=%s", order_id_str)
        raise HTTPException(status_code=500, detail="Failed to process payment")

    if result["notification_order"] is not None:
        background_tasks.add_task(
            notification_service.create_notification_for_order_event, result["notification_order"], "confirmed"
        )

    payment = result["payment"]
    return {
        "paymentStatus": payment["status"],
        "orderStatus": result["order_status"],
        "amount": payment["amount"],
        "simulatedReference": payment.get("simulated_reference"),
        "paidAt": payment.get("paid_at"),
    }
