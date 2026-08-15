"""Real-HTTP integration coverage for the AI Bakery Manager routes'
authorization boundary -- Preview open to any authenticated staff member,
Execute restricted to the `admin` role, through the actual FastAPI
dependency chain (same pattern as test_admin_authorization_route.py; see
that file's own docstring for why get_admin_by_token is patched at
`app.core.security.get_admin_by_token`, not at its origin in
auth_service). Run from `backend/`:

    python -m tests.test_admin_bakery_manager_route
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.auth_service import AdminIdentity

client = TestClient(app)

_STAFF = AdminIdentity(id="staff-1", email="staff@maisondegateau.fr", role="staff", access_token="staff-token")
_ADMIN = AdminIdentity(id="admin-1", email="admin@maisondegateau.fr", role="admin", access_token="admin-token")

_FAKE_PLAN = {
    "runId": "run-1", "timestamp": "2026-08-15T00:00:00+00:00", "mode": "preview",
    "operationalSummary": "Quiet day.", "proposedActions": [],
    "recommendations": {"staffing": [], "inventory": [], "workload": [], "production": []},
    "exceptions": [],
}


def _resolve_identity(token: str):
    return {"staff-token": _STAFF, "admin-token": _ADMIN}.get(token)


def test_authenticated_staff_can_preview():
    with (
        patch("app.core.security.get_admin_by_token", side_effect=_resolve_identity),
        patch("app.api.routes.admin.bakery_manager.bakery_manager_service.get_preview_plan", return_value=_FAKE_PLAN),
    ):
        response = client.post("/admin/bakery-manager/preview", headers={"Authorization": "Bearer staff-token"})
    assert response.status_code == 200
    assert response.json()["runId"] == "run-1"


def test_unauthenticated_cannot_preview():
    response = client.post("/admin/bakery-manager/preview")
    assert response.status_code == 401


def test_staff_cannot_execute():
    with patch("app.core.security.get_admin_by_token", side_effect=_resolve_identity):
        response = client.post(
            "/admin/bakery-manager/execute",
            json={"runId": "run-1", "actions": []},
            headers={"Authorization": "Bearer staff-token"},
        )
    assert response.status_code == 403


def test_admin_can_execute():
    with (
        patch("app.core.security.get_admin_by_token", side_effect=_resolve_identity),
        patch("app.api.routes.admin.bakery_manager.bakery_manager_service.execute_plan", return_value=[]),
    ):
        response = client.post(
            "/admin/bakery-manager/execute",
            json={"runId": "run-1", "actions": []},
            headers={"Authorization": "Bearer admin-token"},
        )
    assert response.status_code == 200
    assert response.json()["runId"] == "run-1"


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
