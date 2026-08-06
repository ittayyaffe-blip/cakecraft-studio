"""Admin customer management routes — Epic 1.2, Customer Management & CRM.

List, profile, order history, timeline, and two placeholder panels
(communications, AI insights) whose real implementations land in later
phases (Master_Blueprint_v1.md §10 and §9 respectively).

Every route depends on `get_current_admin` (Phase 1's reusable dependency),
matching every other `/admin/*` route — nothing here re-implements auth.
This entire screen is read-only: no route mutates anything, so none of
them call `audit_service.record_event` — there is nothing to log yet
(compare `admin/orders.py`'s status-update route, which does mutate and
does log).
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import get_current_admin
from app.schemas.admin_customer import (
    AdminCustomerDetail,
    AdminCustomerListResponse,
    CustomerAIInsightsResponse,
    CustomerCommunicationsResponse,
    CustomerTimelineEvent,
)
from app.schemas.admin_order import AdminOrderSummary
from app.services import customer_service, order_service
from app.services.auth_service import AdminIdentity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/customers", tags=["admin-customers"])


def _require_existing_customer(customer_id: str) -> dict:
    """Shared existence check for every /{customer_id}/... sub-resource
    route below — each one independently confirms the customer exists
    (rather than trusting a prior call did) so every endpoint is correct
    and complete on its own, the same defensive pattern
    admin/orders.py's status-update route already uses.
    """
    try:
        customer = customer_service.get_customer_by_id(customer_id)
    except Exception:
        logger.exception("Failed to fetch customer")
        raise HTTPException(status_code=500, detail="Failed to fetch customer")

    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


@router.get("", response_model=AdminCustomerListResponse)
def list_customers(
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    admin: AdminIdentity = Depends(get_current_admin),
):
    try:
        return customer_service.list_customers(search=search, page=page, page_size=pageSize)
    except Exception:
        logger.exception("Failed to list customers")
        raise HTTPException(status_code=500, detail="Failed to list customers")


@router.get("/{customer_id}", response_model=AdminCustomerDetail)
def get_customer(customer_id: uuid.UUID, admin: AdminIdentity = Depends(get_current_admin)):
    try:
        customer = customer_service.get_customer_detail(str(customer_id))
    except Exception:
        logger.exception("Failed to fetch customer")
        raise HTTPException(status_code=500, detail="Failed to fetch customer")

    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


@router.get("/{customer_id}/orders", response_model=list[AdminOrderSummary])
def get_customer_orders(customer_id: uuid.UUID, admin: AdminIdentity = Depends(get_current_admin)):
    _require_existing_customer(str(customer_id))
    try:
        return order_service.get_orders_for_customer(str(customer_id))
    except Exception:
        logger.exception("Failed to fetch customer orders")
        raise HTTPException(status_code=500, detail="Failed to fetch customer orders")


@router.get("/{customer_id}/timeline", response_model=list[CustomerTimelineEvent])
def get_customer_timeline(customer_id: uuid.UUID, admin: AdminIdentity = Depends(get_current_admin)):
    _require_existing_customer(str(customer_id))
    try:
        return customer_service.get_customer_timeline(str(customer_id))
    except Exception:
        logger.exception("Failed to fetch customer timeline")
        raise HTTPException(status_code=500, detail="Failed to fetch customer timeline")


@router.get("/{customer_id}/communications", response_model=CustomerCommunicationsResponse)
def get_customer_communications(
    customer_id: uuid.UUID, admin: AdminIdentity = Depends(get_current_admin)
):
    _require_existing_customer(str(customer_id))
    return customer_service.get_customer_communications(str(customer_id))


@router.get("/{customer_id}/ai-insights", response_model=CustomerAIInsightsResponse)
def get_customer_ai_insights(
    customer_id: uuid.UUID, admin: AdminIdentity = Depends(get_current_admin)
):
    _require_existing_customer(str(customer_id))
    return customer_service.get_customer_ai_insights(str(customer_id))
