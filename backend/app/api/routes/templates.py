import logging

from fastapi import APIRouter, HTTPException

from app.schemas.template import CakeTemplateResponse
from app.services.template_service import get_active_templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=list[CakeTemplateResponse])
def get_templates():
    try:
        return get_active_templates()
    except Exception:
        logger.exception("Failed to fetch cake templates")
        raise HTTPException(status_code=500, detail="Failed to fetch cake templates")
