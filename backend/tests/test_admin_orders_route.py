"""Real-HTTP integration coverage for the admin Orders routes' new
priority serialization -- through the actual FastAPI dependency chain
(same pattern as test_admin_bakery_manager_route.py; see that file's own
docstring for why get_admin_by_token is patched at
`app.core.security.get_admin_by_token`, not at its origin in
auth_service). Run from `backend/`:

    python -m tests.test_admin_orders_route
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.auth_service import AdminIdentity

client = TestClient(app)

_STAFF = AdminIdentity(id="staff-1", email="staff@maisondegateau.fr", role="staff", access_token="staff-token")

_HEADERS = {"Authorization": "Bearer staff-token"}


def _resolve_identity(token: str):
    return {"staff-token": _STAFF}.get(token)


_ORDER_MISSING_PICKUP = {
    "id": "order-1", "status": "confirmed", "total_price": 100.0,
    "created_at": "2026-08-15T10:00:00+00:00", "pickup_date": None, "pickup_time": None,
    "customers": {"id": "cust-1", "name": "Jane Doe", "email": "jane@example.com", "phone": None},
    "cake_templates": {"id": "tmpl-1", "name": "Rose Cake", "category": "Birthday", "preview_image": None},
    "configuration": {}, "notes": None,
}


def test_orders_list_includes_priority_fields():
    with (
        patch("app.core.security.get_admin_by_token", side_effect=_resolve_identity),
        patch(
            "app.api.routes.admin.orders.order_service.list_orders",
            return_value={"items": [_ORDER_MISSING_PICKUP], "total": 1, "page": 1, "pageSize": 20},
        ),
    ):
        response = client.get("/admin/orders", headers=_HEADERS)

    assert response.status_code == 200
    item = response.json()["items"][0]
    # Missing pickup_date on a confirmed order: priority stays null
    # (never guessed) while manager_attention flags it for review --
    # exactly the policy's NEEDS INFO distinction, at the real API boundary.
    assert item["priority"] is None
    assert item["priority_reason"] == "Pickup date missing — priority cannot be determined."
    assert item["manager_attention"] is True


def test_order_detail_includes_priority_fields():
    with (
        patch("app.core.security.get_admin_by_token", side_effect=_resolve_identity),
        patch(
            "app.api.routes.admin.orders.order_service.get_order_by_id",
            return_value={**_ORDER_MISSING_PICKUP, "pickup_date": "2020-01-01"},
        ),
        patch("app.api.routes.admin.orders.payment_service.get_payment_for_order", return_value=None),
    ):
        response = client.get(f"/admin/orders/{'a' * 8}-{'b' * 4}-{'c' * 4}-{'d' * 4}-{'e' * 12}", headers=_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["priority"] == "CRITICAL"
    assert body["manager_attention"] is True


def test_unauthenticated_cannot_list_orders():
    response = client.get("/admin/orders")
    assert response.status_code == 401


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
