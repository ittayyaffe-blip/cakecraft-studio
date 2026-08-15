"""Real-HTTP integration coverage for the one role-gated admin action
(POST /admin/notifications/{id}/approve) -- proves the FULL FastAPI
dependency chain (route -> Depends(require_role("admin")) ->
Depends(get_current_admin) -> Depends(get_bearer_token) ->
app.core.security.get_admin_by_token) actually rejects a non-admin
staff member's real HTTP request, not just require_role() as a bare
function call (already unit-tested in test_security_dependencies.py --
this is the missing integration-level layer identified by the Final
Security & License Audit).

get_admin_by_token is patched at `app.core.security.get_admin_by_token`
-- where security.py looked it up via `from ... import get_admin_by_token`
-- not at its origin in auth_service, since patching the origin wouldn't
affect security.py's already-bound local name (this project's tests
consistently patch at the exact call-site module, see e.g.
test_webhooks_twilio_route.py's own docstring on the same idea). Run
from `backend/`:

    python -m tests.test_admin_authorization_route
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.auth_service import AdminIdentity

client = TestClient(app)

_STAFF = AdminIdentity(id="staff-1", email="staff@maisondegateau.fr", role="staff", access_token="staff-token")
_ADMIN = AdminIdentity(id="admin-1", email="admin@maisondegateau.fr", role="admin", access_token="admin-token")
_NOTIFICATION_ID = "11111111-1111-1111-1111-111111111111"
_FAKE_NOTIFICATION = {
    "id": _NOTIFICATION_ID, "status": "awaiting_approval", "channel": "email",
    "customer_id": "cust-1", "order_id": None, "event": "agent_drafted",
    "created_at": "2026-08-15T00:00:00+00:00",
}


def _resolve_identity(token: str):
    return {"staff-token": _STAFF, "admin-token": _ADMIN}.get(token)


def test_staff_role_is_rejected_with_403_through_the_real_dependency_chain():
    # No notification_service mocking needed here -- role rejection must
    # happen before the route body (and its notification lookup) ever runs.
    with patch("app.core.security.get_admin_by_token", side_effect=_resolve_identity):
        response = client.post(
            f"/admin/notifications/{_NOTIFICATION_ID}/approve",
            headers={"Authorization": "Bearer staff-token"},
        )
    assert response.status_code == 403


def test_missing_token_is_rejected_with_401_through_the_real_dependency_chain():
    response = client.post(f"/admin/notifications/{_NOTIFICATION_ID}/approve")
    assert response.status_code == 401


def test_admin_role_is_permitted_through_the_real_dependency_chain():
    with (
        patch("app.core.security.get_admin_by_token", side_effect=_resolve_identity),
        patch(
            "app.api.routes.admin.notifications.notification_service.get_notification_by_id",
            return_value=_FAKE_NOTIFICATION,
        ),
        patch(
            "app.api.routes.admin.notifications.notification_service.approve",
            return_value={**_FAKE_NOTIFICATION, "status": "approved"},
        ),
        patch("app.api.routes.admin.notifications.record_event"),
    ):
        response = client.post(
            f"/admin/notifications/{_NOTIFICATION_ID}/approve",
            headers={"Authorization": "Bearer admin-token"},
        )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
