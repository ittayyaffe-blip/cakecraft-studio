"""AI Bakery Manager routes — an optional, additive orchestration layer
over the existing deterministic Back Office services. See
app/services/bakery_manager_service.py's own module docstring for the
full architecture.

Preview is read-only and open to any authenticated staff member, same
posture as the existing AI Daily Briefing / Ask AI Agent / RAG routes.
Execute performs real, allowlisted mutations (order status, draft
creation) and is restricted to the `admin` role specifically —
`require_role("admin")`, the same dependency this project's one other
role-gated action (`/admin/notifications/{id}/approve`) already uses.
No new auth model.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_admin, require_role
from app.schemas.admin_bakery_manager import BakeryManagerPlan, ExecutePlanRequest, ExecutePlanResponse
from app.services import bakery_manager_service
from app.services.auth_service import AdminIdentity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/bakery-manager", tags=["admin-bakery-manager"])


@router.post("/preview", response_model=BakeryManagerPlan)
def preview_plan(admin: AdminIdentity = Depends(get_current_admin)):
    try:
        return bakery_manager_service.get_preview_plan(admin.id)
    except Exception:
        logger.exception("AI Bakery Manager preview failed")
        raise HTTPException(status_code=500, detail="AI Bakery Manager couldn't generate a plan right now.")


@router.post("/execute", response_model=ExecutePlanResponse)
def execute_plan(request: ExecutePlanRequest, admin: AdminIdentity = Depends(require_role("admin"))):
    try:
        results = bakery_manager_service.execute_plan(
            admin.id, request.runId, [a.model_dump() for a in request.actions]
        )
    except Exception:
        logger.exception("AI Bakery Manager execution failed")
        raise HTTPException(status_code=500, detail="Failed to execute the approved plan.")

    return {"runId": request.runId, "results": results}
