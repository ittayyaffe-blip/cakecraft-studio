"""Reusable authentication/authorization dependencies for admin routes.

Every `/admin/*` route (and any future protected route, e.g. the AI layer
sketched in the Master Blueprint) protects itself by depending on
`get_current_admin` (any active staff member) or `require_role(...)` (a
specific role) from this module — no route should re-implement token
parsing or role checks itself. This is the "reusable middleware" the
Phase 1 architecture goals ask for: adding a new admin route means adding
`Depends(get_current_admin)` or `Depends(require_role("admin"))` to it, not
writing new auth logic.
"""

from fastapi import Depends, Header, HTTPException

from app.services.auth_service import AdminIdentity, get_admin_by_token


def get_bearer_token(authorization: str | None = Header(default=None)) -> str:
    """Extract the raw token from an `Authorization: Bearer <token>` header."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    return authorization.split(" ", 1)[1].strip()


def get_current_admin(token: str = Depends(get_bearer_token)) -> AdminIdentity:
    """Resolve the calling admin/staff identity from a bearer token.

    A valid Supabase Auth session alone is not enough to reach an admin
    route: the token's user must also have a matching, active
    `staff_profiles` row (checked inside `get_admin_by_token`), or this
    raises 401 exactly as if the token were invalid.
    """
    admin = get_admin_by_token(token)
    if admin is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return admin


def require_role(*roles: str):
    """Dependency factory restricting a route to specific staff roles.

    Usage on any future admin-only route:

        @router.delete("/admin/catalog/{id}")
        def delete_template(admin: AdminIdentity = Depends(require_role("admin"))):
            ...

    Raises 403 if the caller is authenticated as staff but not one of the
    given roles; 401 (via `get_current_admin`) if not authenticated at all.
    """

    def _check(admin: AdminIdentity = Depends(get_current_admin)) -> AdminIdentity:
        if admin.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient role for this action")
        return admin

    return _check
