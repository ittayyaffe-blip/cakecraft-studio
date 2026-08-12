"""Admin Catalog Management routes — Master_Blueprint_v1.md §17 Phase 5.

Read-only foundation slice: staff can see the full catalog (active and
inactive templates, plus the full customization-options catalog) without
touching the database directly. Create/update/deactivate/option-editing
are later, separate steps on top of this one.

Same auth pattern as every other admin route: `get_current_admin` only —
this is a read, not the kind of business-judgment action (like approving a
notification) that warrants `require_role("admin")` — see
app.core.security's own docstring and FINAL_ARCHITECTURE.md §12.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_admin
from app.schemas.admin_catalog import AdminCakeTemplateWithOptions
from app.services import template_service
from app.services.auth_service import AdminIdentity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/catalog", tags=["admin-catalog"])


@router.get("/templates", response_model=list[AdminCakeTemplateWithOptions])
def list_templates(admin: AdminIdentity = Depends(get_current_admin)):
    try:
        return template_service.get_all_templates_with_options()
    except Exception:
        logger.exception("Failed to list catalog templates")
        raise HTTPException(status_code=500, detail="Failed to list catalog templates")
