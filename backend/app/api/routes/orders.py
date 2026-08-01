import logging

from fastapi import APIRouter, HTTPException

from app.schemas.order import OrderCreateRequest, OrderCreateResponse
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

    return {"orderId": order_id}
