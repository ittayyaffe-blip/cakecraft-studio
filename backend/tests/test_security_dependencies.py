"""Dependency-free self-check for `app.core.security` — no live Supabase
connection, no test framework required. Run from `backend/`:

    python -m tests.test_security_dependencies

Covers the pure logic only: bearer-header parsing and role gating. Token
verification itself (`get_current_admin` -> `auth_service.get_admin_by_token`)
calls Supabase Auth over the network and is exercised manually against a
running server instead — see docs/PHASE1_IDENTITY_SECURITY.md.
"""

from fastapi import HTTPException

from app.core.security import get_bearer_token, require_role
from app.services.auth_service import AdminIdentity


def _expect_http_error(fn, status_code: int) -> None:
    try:
        fn()
    except HTTPException as exc:
        assert exc.status_code == status_code, f"expected {status_code}, got {exc.status_code}"
    else:
        raise AssertionError("expected HTTPException, none was raised")


def test_get_bearer_token_extracts_token():
    assert get_bearer_token(authorization="Bearer abc123") == "abc123"


def test_get_bearer_token_accepts_case_insensitive_scheme():
    assert get_bearer_token(authorization="bearer abc123") == "abc123"


def test_get_bearer_token_rejects_missing_header():
    _expect_http_error(lambda: get_bearer_token(authorization=None), 401)


def test_get_bearer_token_rejects_malformed_header():
    _expect_http_error(lambda: get_bearer_token(authorization="Token abc123"), 401)


def test_require_role_allows_matching_role():
    admin = AdminIdentity(id="1", email="a@b.com", role="admin", access_token="t")
    check = require_role("admin")
    assert check(admin=admin) is admin


def test_require_role_allows_any_of_multiple_roles():
    staff = AdminIdentity(id="1", email="a@b.com", role="staff", access_token="t")
    check = require_role("admin", "staff")
    assert check(admin=staff) is staff


def test_require_role_rejects_other_role():
    staff = AdminIdentity(id="1", email="a@b.com", role="staff", access_token="t")
    check = require_role("admin")
    _expect_http_error(lambda: check(admin=staff), 403)


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
