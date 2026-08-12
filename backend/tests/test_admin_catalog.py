"""Dependency-free self-check for `app.api.routes.admin.catalog` -- the
Catalog Management read-only foundation slice (Master_Blueprint_v1.md §17
Phase 5). Run from `backend/`:

    python -m tests.test_admin_catalog

template_service.get_all_templates_with_options is mocked at its exact
call boundary (same convention every other route test module in this
project uses) so the route's own wiring runs for real; the service's own
logic is covered in test_template_service.py.

Auth: this project's admin routes are never exercised end-to-end through
a live ASGI request in the automated suite (get_current_admin's own token
verification calls Supabase Auth over the network -- see
test_security_dependencies.py's docstring on why that's tested live
instead). Consistent with that, "unauthenticated is rejected" here means
two things: (1) this route is actually wired to the same
`get_current_admin` dependency every other /admin/* route uses, not a
route-specific check, and (2) that dependency's own token-parsing step
(get_bearer_token) rejects a missing/malformed header with 401 -- the
exact mechanism this route relies on.
"""

import inspect
from unittest.mock import patch

from fastapi import HTTPException

from app.api.routes.admin import catalog
from app.core.security import get_bearer_token, get_current_admin
from app.services.auth_service import AdminIdentity

_ADMIN = AdminIdentity(id="staff-1", email="baker@maisondegateau.fr", role="admin", access_token="t")

_TEMPLATE_WITH_OPTIONS = {
    "id": "t1",
    "name": "Ivory Classic",
    "category": "Wedding",
    "style": "Classic",
    "base_price": 250.0,
    "preview_image": None,
    "active": True,
    "customization_options": {
        "cake_sizes": [
            {"id": "s1", "name": "Small", "display_order": 1, "active": True, "price_adjustment": 0, "servings_min": 8, "servings_max": 10}
        ],
        "flavors": [{"id": "f1", "name": "Vanilla", "display_order": 1, "active": True}],
        "fillings": [],
        "frostings": [],
    },
}


def test_list_templates_returns_whatever_the_service_returns():
    with patch.object(catalog.template_service, "get_all_templates_with_options", return_value=[_TEMPLATE_WITH_OPTIONS]) as mock_get:
        result = catalog.list_templates(admin=_ADMIN)

    assert result == [_TEMPLATE_WITH_OPTIONS]
    mock_get.assert_called_once_with()


def test_list_templates_route_is_wired_to_the_shared_admin_dependency():
    # Structural proof this route uses the exact same auth mechanism as
    # every other /admin/* route -- not a route-specific reimplementation.
    admin_param = inspect.signature(catalog.list_templates).parameters["admin"]
    assert admin_param.default.dependency is get_current_admin


def test_missing_bearer_token_is_rejected_with_401():
    # The dependency this route relies on for authentication -- same check
    # as test_security_dependencies.py's own coverage of get_bearer_token,
    # exercised here to confirm it's the mechanism actually guarding this
    # endpoint (see the structural check above).
    try:
        get_bearer_token(authorization=None)
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("expected HTTPException(401), none was raised")


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
