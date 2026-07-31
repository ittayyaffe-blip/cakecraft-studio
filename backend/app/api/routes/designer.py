import logging
import uuid

from fastapi import APIRouter, HTTPException

from app.schemas.designer_options import DesignerInitResponse, DesignerOptionsResponse
from app.services.designer_service import get_designer_initialization, get_designer_options

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/designer", tags=["designer"])


@router.get("/options", response_model=DesignerOptionsResponse)
def get_options():
    try:
        return get_designer_options()
    except Exception:
        logger.exception("Failed to fetch designer options")
        raise HTTPException(status_code=500, detail="Failed to fetch designer options")


@router.get("/{template_id}", response_model=DesignerInitResponse)
def get_designer_init(template_id: uuid.UUID):
    try:
        result = get_designer_initialization(str(template_id))
    except Exception:
        logger.exception("Failed to initialize designer")
        raise HTTPException(status_code=500, detail="Failed to initialize designer")

    if result is None:
        raise HTTPException(status_code=404, detail="Cake template not found")

    return result
