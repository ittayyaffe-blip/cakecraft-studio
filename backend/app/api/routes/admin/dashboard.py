"""Admin dashboard route — one read-only aggregate endpoint.

Protected the same way as every other `/admin/*` route
(`Depends(get_current_admin)`); nothing here mutates data, so there's
nothing to audit-log.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_admin
from app.schemas.admin_dashboard import DashboardResponse
from app.services.auth_service import AdminIdentity
from app.services.dashboard_service import get_dashboard_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin-dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(admin: AdminIdentity = Depends(get_current_admin)):
    try:
        return get_dashboard_data()
    except Exception:
        logger.exception("Failed to load dashboard data")
        raise HTTPException(status_code=500, detail="Failed to load dashboard data")
