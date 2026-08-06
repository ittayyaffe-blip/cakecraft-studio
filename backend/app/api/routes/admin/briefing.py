"""AI Daily Briefing route — one read-only aggregate endpoint, the same
shape as `dashboard.py` (protected the same way, nothing here mutates
data so there's nothing to audit-log). Final AI Intelligence Phase.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_admin
from app.schemas.admin_briefing import DailyBriefing
from app.services.auth_service import AdminIdentity
from app.services.briefing_service import get_daily_briefing

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin-briefing"])


@router.get("/briefing", response_model=DailyBriefing)
def daily_briefing(admin: AdminIdentity = Depends(get_current_admin)):
    try:
        return get_daily_briefing()
    except Exception:
        logger.exception("Failed to compose the daily briefing")
        raise HTTPException(status_code=500, detail="Failed to compose the daily briefing")
