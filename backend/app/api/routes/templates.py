import logging
import uuid

from fastapi import APIRouter, HTTPException

from app.schemas.template import CakeTemplateResponse
from app.services.template_service import get_active_templates, get_template_by_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=list[CakeTemplateResponse])
def get_templates(collection: str | None = None):
    try:
        return get_active_templates(collection)
    except Exception:
        logger.exception("Failed to fetch cake templates")
        raise HTTPException(status_code=500, detail="Failed to fetch cake templates")


@router.get("/{template_id}", response_model=CakeTemplateResponse)
def get_template(template_id: uuid.UUID):
    try:
        template = get_template_by_id(str(template_id))
    except Exception:
        logger.exception("Failed to fetch cake template")
        raise HTTPException(status_code=500, detail="Failed to fetch cake template")

    if template is None:
        raise HTTPException(status_code=404, detail="Cake template not found")

    return template
