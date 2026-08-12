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
import uuid
from unittest.mock import patch

from fastapi import HTTPException

from app.api.routes.admin import catalog
from app.core.security import get_bearer_token, get_current_admin
from app.schemas.admin_catalog import TemplateActiveUpdateRequest, TemplateUpdateRequest
from app.services.auth_service import AdminIdentity

_ADMIN = AdminIdentity(id="staff-1", email="baker@maisondegateau.fr", role="admin", access_token="t")
_TEMPLATE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")

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


# --- set_template_active: Catalog Management Slice 2 -----------------------


def test_set_template_active_updates_and_records_an_audit_event():
    existing = {"id": str(_TEMPLATE_ID), "name": "Ivory Classic", "active": True}
    updated = {**existing, "active": False}
    with (
        patch.object(catalog.template_service, "get_template_by_id", return_value=existing) as mock_get,
        patch.object(catalog.template_service, "set_template_active", return_value=updated) as mock_set,
        patch.object(catalog, "record_event") as mock_record,
    ):
        result = catalog.set_template_active(
            _TEMPLATE_ID, TemplateActiveUpdateRequest(active=False), admin=_ADMIN
        )

    assert result == updated
    mock_get.assert_called_once_with(str(_TEMPLATE_ID))
    mock_set.assert_called_once_with(str(_TEMPLATE_ID), False)
    mock_record.assert_called_once_with(
        actor_id=_ADMIN.id,
        action="template.active_changed",
        entity_type="cake_templates",
        entity_id=str(_TEMPLATE_ID),
        before={"active": True},
        after={"active": False},
    )


def test_set_template_active_404_when_template_not_found():
    with (
        patch.object(catalog.template_service, "get_template_by_id", return_value=None),
        patch.object(catalog.template_service, "set_template_active") as mock_set,
        patch.object(catalog, "record_event") as mock_record,
    ):
        try:
            catalog.set_template_active(_TEMPLATE_ID, TemplateActiveUpdateRequest(active=False), admin=_ADMIN)
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            raise AssertionError("expected HTTPException(404), none was raised")

    mock_set.assert_not_called()  # never attempts the update
    mock_record.assert_not_called()  # never logs an event for a no-op


def test_set_template_active_route_is_wired_to_the_shared_admin_dependency():
    admin_param = inspect.signature(catalog.set_template_active).parameters["admin"]
    assert admin_param.default.dependency is get_current_admin


# --- update_template: Catalog Management Slice 3 ----------------------------


def test_update_template_records_audit_event_containing_only_the_changed_fields():
    existing = {
        "id": str(_TEMPLATE_ID),
        "name": "Ivory Classic",
        "category": "Wedding",
        "style": "Classic",
        "base_price": 250.0,
        "preview_image": None,
        "active": True,
    }
    updated = {**existing, "base_price": 300.0}
    with (
        patch.object(catalog.template_service, "get_template_by_id", return_value=existing) as mock_get,
        patch.object(catalog.template_service, "update_template", return_value=updated) as mock_update,
        patch.object(catalog, "record_event") as mock_record,
    ):
        result = catalog.update_template(
            _TEMPLATE_ID, TemplateUpdateRequest(base_price=300.0), admin=_ADMIN
        )

    assert result == updated
    mock_get.assert_called_once_with(str(_TEMPLATE_ID))
    mock_update.assert_called_once_with(str(_TEMPLATE_ID), {"base_price": 300.0})
    mock_record.assert_called_once_with(
        actor_id=_ADMIN.id,
        action="template.updated",
        entity_type="cake_templates",
        entity_id=str(_TEMPLATE_ID),
        before={"base_price": 250.0},  # only the field that actually changed
        after={"base_price": 300.0},
    )


def test_update_template_explicit_preview_image_null_is_forwarded_as_a_change():
    existing = {"id": str(_TEMPLATE_ID), "preview_image": "https://example.com/old.jpg"}
    updated = {**existing, "preview_image": None}
    with (
        patch.object(catalog.template_service, "get_template_by_id", return_value=existing),
        patch.object(catalog.template_service, "update_template", return_value=updated) as mock_update,
        patch.object(catalog, "record_event") as mock_record,
    ):
        catalog.update_template(_TEMPLATE_ID, TemplateUpdateRequest(preview_image=None), admin=_ADMIN)

    mock_update.assert_called_once_with(str(_TEMPLATE_ID), {"preview_image": None})
    mock_record.assert_called_once_with(
        actor_id=_ADMIN.id,
        action="template.updated",
        entity_type="cake_templates",
        entity_id=str(_TEMPLATE_ID),
        before={"preview_image": "https://example.com/old.jpg"},
        after={"preview_image": None},
    )


def test_update_template_omitted_preview_image_is_never_sent_to_the_service():
    existing = {"id": str(_TEMPLATE_ID), "name": "Old Name", "preview_image": "https://example.com/keep.jpg"}
    updated = {**existing, "name": "New Name"}
    with (
        patch.object(catalog.template_service, "get_template_by_id", return_value=existing),
        patch.object(catalog.template_service, "update_template", return_value=updated) as mock_update,
        patch.object(catalog, "record_event"),
    ):
        catalog.update_template(_TEMPLATE_ID, TemplateUpdateRequest(name="New Name"), admin=_ADMIN)

    sent_fields = mock_update.call_args.args[1]
    assert sent_fields == {"name": "New Name"}
    assert "preview_image" not in sent_fields  # left alone, not overwritten with the unchanged value


def test_update_template_404_when_template_not_found():
    with (
        patch.object(catalog.template_service, "get_template_by_id", return_value=None),
        patch.object(catalog.template_service, "update_template") as mock_update,
        patch.object(catalog, "record_event") as mock_record,
    ):
        try:
            catalog.update_template(_TEMPLATE_ID, TemplateUpdateRequest(name="New Name"), admin=_ADMIN)
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            raise AssertionError("expected HTTPException(404), none was raised")

    mock_update.assert_not_called()
    mock_record.assert_not_called()


def test_update_template_empty_body_is_rejected_as_400_without_recording_an_event():
    # The service is the one place "no fields" is actually validated (see
    # test_template_service.py) -- this confirms the route correctly maps
    # that ValueError to a 400 rather than a 500, and never logs an event
    # for a no-op.
    existing = {"id": str(_TEMPLATE_ID), "name": "Ivory Classic"}
    with (
        patch.object(catalog.template_service, "get_template_by_id", return_value=existing),
        patch.object(catalog.template_service, "update_template", side_effect=ValueError("No fields to update")),
        patch.object(catalog, "record_event") as mock_record,
    ):
        try:
            catalog.update_template(_TEMPLATE_ID, TemplateUpdateRequest(), admin=_ADMIN)
        except HTTPException as exc:
            assert exc.status_code == 400
        else:
            raise AssertionError("expected HTTPException(400), none was raised")

    mock_record.assert_not_called()


def test_update_template_route_is_wired_to_the_shared_admin_dependency():
    admin_param = inspect.signature(catalog.update_template).parameters["admin"]
    assert admin_param.default.dependency is get_current_admin


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
