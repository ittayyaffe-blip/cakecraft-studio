import logging

from fastapi import APIRouter, HTTPException

from app.core.database import supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("")
def get_templates():
    try:
        response = (
            supabase.table("cake_templates")
            .select("*")
            .eq("active", True)
            .order("name")
            .execute()
        )
    except Exception:
        logger.exception("Failed to fetch cake templates")
        raise HTTPException(status_code=500, detail="Failed to fetch cake templates")

    return response.data
