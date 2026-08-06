"""Admin authentication routes: login, logout, and "who am I" (`/admin/me`).

This is the only route module that calls `auth_service.login`/`.logout`
directly. Every *other* current or future `/admin/*` route protects itself
declaratively via `Depends(get_current_admin)` / `Depends(require_role(...))`
from `app.core.security` instead — see that module's docstring.

Error-handling follows the same convention as every other route in this
project (`app/api/routes/orders.py` etc.): known, expected failures map to
a specific status code, anything unexpected is logged and returned as 500.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_admin
from app.schemas.admin_auth import (
    AdminLoginRequest,
    AdminLoginResponse,
    AdminLogoutResponse,
    AdminUser,
)
from app.services import auth_service
from app.services.audit_service import record_event
from app.services.auth_service import AdminIdentity, InvalidCredentialsError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin-auth"])


@router.post("/login", response_model=AdminLoginResponse)
def login(credentials: AdminLoginRequest):
    try:
        result = auth_service.login(credentials.email, credentials.password)
    except InvalidCredentialsError:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    except Exception:
        logger.exception("Admin login failed")
        raise HTTPException(status_code=500, detail="Login failed")

    admin: AdminIdentity = result["user"]

    # Framework-only logging call (Phase 1 goal 6): every future admin
    # action should call record_event the same way, right after the action
    # it describes succeeds.
    record_event(
        actor_id=admin.id,
        action="admin.login",
        entity_type="staff_profiles",
        entity_id=admin.id,
    )

    return {
        "access_token": result["access_token"],
        "refresh_token": result["refresh_token"],
        "expires_in": result["expires_in"],
        "user": {"id": admin.id, "email": admin.email, "role": admin.role},
    }


@router.post("/logout", response_model=AdminLogoutResponse)
def logout(admin: AdminIdentity = Depends(get_current_admin)):
    try:
        auth_service.logout(admin)
    except Exception:
        logger.exception("Admin logout failed")
        raise HTTPException(status_code=500, detail="Logout failed")

    record_event(
        actor_id=admin.id,
        action="admin.logout",
        entity_type="staff_profiles",
        entity_id=admin.id,
    )
    return {"message": "Logged out"}


@router.get("/me", response_model=AdminUser)
def me(admin: AdminIdentity = Depends(get_current_admin)):
    """Returns the caller's own identity — mainly useful to verify a token/role
    without needing a Backoffice UI (not built in this phase)."""
    return {"id": admin.id, "email": admin.email, "role": admin.role}
