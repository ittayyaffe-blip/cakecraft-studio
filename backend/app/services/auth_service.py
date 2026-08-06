"""Admin authentication service — the only module that talks to Supabase Auth.

Identity (email + password) lives entirely in Supabase Auth; this codebase
never stores a password. `public.staff_profiles` (see the Phase 1 migration)
only maps an already-authenticated Supabase Auth user to an app-level role —
a valid Supabase Auth login is necessary but not sufficient to reach an
admin route, the user must also have a matching, active `staff_profiles`
row (checked by `get_admin_by_token`, used by every protected route via
`app.core.security`).

Customers are never touched by this module: they have no accounts, and
nothing here runs on any customer-facing request path.
"""

from dataclasses import dataclass

from supabase import AuthApiError, create_client

from app.core.config import settings
from app.core.database import supabase


class InvalidCredentialsError(Exception):
    """Raised when email/password login fails, or the account isn't an active staff member."""


@dataclass(frozen=True)
class AdminIdentity:
    """The resolved identity of an authenticated, active staff member."""

    id: str
    email: str
    role: str
    access_token: str


def _get_staff_profile(user_id: str) -> dict | None:
    response = (
        supabase.table("staff_profiles")
        .select("user_id, name, role, active")
        .eq("user_id", user_id)
        .eq("active", True)
        .maybe_single()
        .execute()
    )
    return response.data if response is not None else None


def login(email: str, password: str) -> dict:
    """Authenticate a staff member against Supabase Auth and return a session.

    Uses a fresh, throwaway Supabase client rather than the shared
    `app.core.database.supabase` singleton. `sign_in_with_password` stores
    the resulting session as state on the client instance it's called on;
    the singleton is shared across every concurrent request, so reusing it
    here would let concurrent logins race on that shared state. A new
    client per login call keeps the mutation isolated to this one request.
    """
    login_client = create_client(settings.supabase_url, settings.supabase_key)

    try:
        result = login_client.auth.sign_in_with_password({"email": email, "password": password})
    except AuthApiError as exc:
        raise InvalidCredentialsError(str(exc)) from exc

    if result.session is None or result.user is None:
        raise InvalidCredentialsError("Login did not return a session")

    profile = _get_staff_profile(result.user.id)
    if profile is None:
        raise InvalidCredentialsError("Not a recognized, active staff account")

    return {
        "access_token": result.session.access_token,
        "refresh_token": result.session.refresh_token,
        "expires_in": result.session.expires_in,
        "user": AdminIdentity(
            id=result.user.id,
            email=result.user.email,
            role=profile["role"],
            access_token=result.session.access_token,
        ),
    }


def get_admin_by_token(access_token: str) -> AdminIdentity | None:
    """Resolve a bearer token to an active staff identity, or None.

    Returns None (never raises) for an invalid/expired token, or a token
    that belongs to a real Supabase Auth user with no matching active
    `staff_profiles` row — both are simply "not an admin" to the caller.
    Used by every protected `/admin/*` route via `app.core.security`.
    """
    try:
        user_response = supabase.auth.get_user(jwt=access_token)
    except AuthApiError:
        return None

    if user_response is None or user_response.user is None:
        return None

    profile = _get_staff_profile(user_response.user.id)
    if profile is None:
        return None

    return AdminIdentity(
        id=user_response.user.id,
        email=user_response.user.email,
        role=profile["role"],
        access_token=access_token,
    )


def logout(admin: AdminIdentity) -> None:
    """Revoke the given admin's session server-side via Supabase Auth.

    `admin.access_token` is passed explicitly to `auth.admin.sign_out`
    (the service-role "revoke someone else's session" call, safe to run on
    the shared singleton since it takes the token as a parameter rather
    than reading it from client-instance state) instead of the plain
    `auth.sign_out()`, which only ever signs out whatever session happens
    to be stored on the client instance it's called on.
    """
    supabase.auth.admin.sign_out(admin.access_token, settings.admin_signout_scope)
