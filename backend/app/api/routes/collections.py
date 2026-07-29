import logging

from fastapi import APIRouter, HTTPException

from app.schemas.collection import CollectionResponse
from app.services.collection_service import get_active_collections

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/collections", tags=["collections"])


@router.get("", response_model=list[CollectionResponse])
def get_collections():
    try:
        return get_active_collections()
    except Exception:
        logger.exception("Failed to fetch collections")
        raise HTTPException(status_code=500, detail="Failed to fetch collections")
