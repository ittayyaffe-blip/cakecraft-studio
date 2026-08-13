"""Dependency-free self-check for the new `GET /admin/communications/
whatsapp-status` route -- app.api.routes.admin.communications's
pre-existing check-email/inbox routes have no dedicated route-level test
file (only exercised indirectly via test_inbound_service.py), matching
this project's existing pattern of not every route module having one;
this file covers only the endpoint added for the Twilio WhatsApp Sandbox
integration. Run from `backend/`:

    python -m tests.test_admin_communications_route
"""

from unittest.mock import patch

from app.api.routes.admin import communications
from app.services.auth_service import AdminIdentity

_ADMIN = AdminIdentity(id="staff-1", email="baker@maisondegateau.fr", role="admin", access_token="t")


def test_whatsapp_status_route_returns_whatever_the_service_reports():
    fake_status = {"configured": True, "provider": "twilio_sandbox", "sandboxNumber": "+14155238886"}
    with patch.object(communications.communication, "whatsapp_status", return_value=fake_status) as mock_status:
        result = communications.whatsapp_status(admin=_ADMIN)

    assert result == fake_status
    mock_status.assert_called_once_with()


def test_whatsapp_status_route_reports_unconfigured_state_too():
    fake_status = {"configured": False, "provider": None, "sandboxNumber": None}
    with patch.object(communications.communication, "whatsapp_status", return_value=fake_status):
        result = communications.whatsapp_status(admin=_ADMIN)

    assert result["configured"] is False


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
