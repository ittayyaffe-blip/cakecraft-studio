"""Admin Catalog Management routes — Master_Blueprint_v1.md §17 Phase 5.

Slice 1 (read-only): staff can see the full catalog (active and inactive
templates, plus the full customization-options catalog) without touching
the database directly.

Slice 2 (this addition): staff can activate/deactivate a template. Follows
admin/orders.py's status-update route exactly — fetch-existing (for the
audit "before" snapshot) -> update -> `record_event` -> return the
refreshed row — the same "service does the work, route logs the event
right after" pattern, applied to `cake_templates` instead of `orders`, the
exact future entity_type audit_service.py's own docstring already named.
Create/edit/delete and any customization-option change are later,
separate steps on top of this one.

Same auth pattern as every other admin route: `get_current_admin` only —
these are not the kind of business-judgment action (like approving a
notification) that warrants `require_role("admin")` — see
app.core.security's own docstring and FINAL_ARCHITECTURE.md §12.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_admin
from app.schemas.admin_catalog import AdminCakeTemplateWithOptions, TemplateActiveUpdateRequest
from app.schemas.template import CakeTemplateResponse
from app.services import template_service
from app.services.auth_service import AdminIdentity
from app.services.audit_service import record_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/catalog", tags=["admin-catalog"])


@router.get("/templates", response_model=list[AdminCakeTemplateWithOptions])
def list_templates(admin: AdminIdentity = Depends(get_current_admin)):
    try:
        return template_service.get_all_templates_with_options()
    except Exception:
        logger.exception("Failed to list catalog templates")
        raise HTTPException(status_code=500, detail="Failed to list catalog templates")


@router.patch("/templates/{template_id}/active", response_model=CakeTemplateResponse)
def set_template_active(
    template_id: uuid.UUID,
    body: TemplateActiveUpdateRequest,
    admin: AdminIdentity = Depends(get_current_admin),
):
    template_id_str = str(template_id)

    try:
        existing = template_service.get_template_by_id(template_id_str)
    except Exception:
        logger.exception("Failed to fetch template")
        raise HTTPException(status_code=500, detail="Failed to fetch template")

    if existing is None:
        raise HTTPException(status_code=404, detail="Template not found")

    try:
        updated = template_service.set_template_active(template_id_str, body.active)
    except Exception:
        logger.exception("Failed to update template active flag")
        raise HTTPException(status_code=500, detail="Failed to update template active flag")

    record_event(
        actor_id=admin.id,
        action="template.active_changed",
        entity_type="cake_templates",
        entity_id=template_id_str,
        before={"active": existing["active"]},
        after={"active": body.active},
    )

    return updated
