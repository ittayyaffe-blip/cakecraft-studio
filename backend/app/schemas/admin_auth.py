"""Request/response schemas for admin authentication (`app/api/routes/admin/auth.py`).

`email`/`password` are typed as plain `str`, mirroring the convention
already used for `OrderCreateRequest.customer_email` in `app/schemas/order.py`,
rather than introducing `pydantic.EmailStr` — that would pull in a new
dependency (`email-validator`) that isn't currently installed. Real format
validation happens where it already does for orders: Supabase Auth itself
rejects a malformed email on login.
"""

from pydantic import BaseModel


class AdminLoginRequest(BaseModel):
    email: str
    password: str


class AdminUser(BaseModel):
    """The identity returned to the client — never includes the access token."""

    id: str
    email: str
    role: str


class AdminLoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AdminUser


class AdminLogoutResponse(BaseModel):
    message: str
