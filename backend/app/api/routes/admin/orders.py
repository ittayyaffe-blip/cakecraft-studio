"""Admin order management routes: list (search/filter/paginate), detail,
and status updates.

Every route depends on `get_current_admin` (Phase 1's reusable dependency —
see `app/core/security.py`) and nothing here re-implements auth. The status
update route additionally writes to the audit log via
`app/services/audit_service.py`, following the exact same
"service does the work, route logs the event right after" pattern already
established for admin login/logout in `app/api/routes/admin/auth.py`.

The status-update route is also where the Event-Driven Customer
Communication Platform's queue is fed from: after a status change is
applied and audited, `notification_service.create_notification_for_order_event`
creates (and drafts) a notification for that transition, if it's one
customers care about. See docs/SPRINT1_EVENT_DRIVEN_COMMUNICATION.md.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import get_current_admin
from app.schemas.admin_order import (
    AdminOrderDetail,
    AdminOrderListResponse,
    OrderStatusUpdateRequest,
)
from app.services import notification_service, order_service, payment_service
from app.services.auth_service import AdminIdentity
from app.services.audit_service import record_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/orders", tags=["admin-orders"])


@router.get("", response_model=AdminOrderListResponse)
def list_orders(
    search: str | None = None,
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    admin: AdminIdentity = Depends(get_current_admin),
):
    if status is not None and status not in order_service.ORDER_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    try:
        return order_service.list_orders(search=search, status=status, page=page, page_size=pageSize)
    except Exception:
        logger.exception("Failed to list orders")
        raise HTTPException(status_code=500, detail="Failed to list orders")


@router.get("/{order_id}", response_model=AdminOrderDetail)
def get_order(order_id: uuid.UUID, admin: AdminIdentity = Depends(get_current_admin)):
    order_id_str = str(order_id)
    try:
        order = order_service.get_order_by_id(order_id_str)
    except Exception:
        logger.exception("Failed to fetch order")
        raise HTTPException(status_code=500, detail="Failed to fetch order")

    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    payment = payment_service.get_payment_for_order(order_id_str)
    return {**order, "payment": payment}


@router.patch("/{order_id}/status", response_model=AdminOrderDetail)
def update_order_status(
    order_id: uuid.UUID,
    body: OrderStatusUpdateRequest,
    admin: AdminIdentity = Depends(get_current_admin),
):
    order_id_str = str(order_id)

    try:
        existing = order_service.get_order_by_id(order_id_str)
    except Exception:
        logger.exception("Failed to fetch order")
        raise HTTPException(status_code=500, detail="Failed to fetch order")

    if existing is None:
        raise HTTPException(status_code=404, detail="Order not found")

    try:
        updated = order_service.update_order_status(order_id_str, body.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Failed to update order status")
        raise HTTPException(status_code=500, detail="Failed to update order status")

    record_event(
        actor_id=admin.id,
        action="order.status_changed",
        entity_type="orders",
        entity_id=order_id_str,
        before={"status": existing["status"]},
        after={"status": body.status},
    )

    # Event-Driven Customer Communication Platform: queue + render a
    # notification for this transition, if it's one customers care about.
    # Fails safe (see its docstring) — never blocks the status update above.
    notification_service.create_notification_for_order_event(updated, body.status)

    return updated
