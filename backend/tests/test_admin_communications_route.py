"""Dependency-free self-check for admin/communications.py's WhatsApp
routes -- the pre-existing check-email/inbox routes have no dedicated
route-level test file (only exercised indirectly via
test_inbound_service.py), matching this project's existing pattern of
not every route module having one; this file covers only the endpoints
added for the Twilio WhatsApp Sandbox integration and the Communications
Workspace's WhatsApp thread view. Run from `backend/`:

    python -m tests.test_admin_communications_route
"""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api.routes.admin import communications
from app.schemas.admin_communications import WhatsAppReplyRequest
from app.services.auth_service import AdminIdentity

_ADMIN = AdminIdentity(id="staff-1", email="baker@maisondegateau.fr", role="admin", access_token="t")
_CUSTOMER = {"id": "cust-1", "name": "Jane Doe", "email": "jane@example.com", "phone": "+972545446601"}


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


# --- GET /whatsapp/thread/{customer_id} -------------------------------------


def test_whatsapp_thread_merges_and_sorts_incoming_and_outgoing_by_time():
    incoming = [{"id": "in-1", "body": "Is my cake ready?", "received_at": "2026-01-01T10:00:00+00:00"}]
    outgoing = [
        {"body": "Yes, ready for pickup!", "subject": None, "created_at": "2026-01-01T09:00:00+00:00", "sent_at": "2026-01-01T11:00:00+00:00", "status": "sent", "channel": "whatsapp"},
        {"body": "This one's email, must be excluded", "subject": None, "created_at": "2026-01-01T08:00:00+00:00", "sent_at": None, "status": "draft", "channel": "email"},
    ]
    with (
        patch.object(communications.customer_service, "get_customer_by_id", return_value=_CUSTOMER),
        patch.object(communications.inbound_service, "list_channel_messages_for_customer", return_value=incoming) as mock_incoming,
        patch.object(communications.notification_service, "list_notifications_for_customer", return_value=outgoing),
    ):
        result = communications.whatsapp_thread("cust-1", admin=_ADMIN)

    mock_incoming.assert_called_once_with("cust-1", "whatsapp")
    assert result["customer"] == _CUSTOMER
    # Only the whatsapp-channel outgoing message survives the filter, and
    # ordering follows actual timestamp (sent_at for outgoing), not insertion
    # order -- the incoming message arrived at 10:00, the surviving outgoing
    # one was sent at 11:00, so incoming comes first despite being requested second.
    assert len(result["messages"]) == 2
    assert result["messages"][0]["direction"] == "incoming"
    assert result["messages"][1]["direction"] == "outgoing"
    assert result["messages"][1]["body"] == "Yes, ready for pickup!"


def test_whatsapp_thread_404_for_unknown_customer():
    with patch.object(communications.customer_service, "get_customer_by_id", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            communications.whatsapp_thread("no-such-customer", admin=_ADMIN)
    assert exc_info.value.status_code == 404


# --- POST /whatsapp/reply ----------------------------------------------------


def test_whatsapp_reply_creates_a_draft_and_returns_it():
    created = {"id": "notif-1", "customer_id": "cust-1", "channel": "whatsapp", "status": "draft", "body": "On its way!"}
    with (
        patch.object(communications.customer_service, "get_customer_by_id", return_value=_CUSTOMER),
        patch.object(communications.notification_service, "create_staff_message", return_value=created) as mock_create,
    ):
        result = communications.whatsapp_reply(WhatsAppReplyRequest(customerId="cust-1", body="On its way!"), admin=_ADMIN)

    assert result == created
    mock_create.assert_called_once_with("cust-1", "whatsapp", "On its way!")


def test_whatsapp_reply_rejects_empty_body():
    with patch.object(communications.customer_service, "get_customer_by_id", return_value=_CUSTOMER):
        with pytest.raises(HTTPException) as exc_info:
            communications.whatsapp_reply(WhatsAppReplyRequest(customerId="cust-1", body="   "), admin=_ADMIN)
    assert exc_info.value.status_code == 400


def test_whatsapp_reply_404_for_unknown_customer():
    with patch.object(communications.customer_service, "get_customer_by_id", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            communications.whatsapp_reply(WhatsAppReplyRequest(customerId="no-such-customer", body="hi"), admin=_ADMIN)
    assert exc_info.value.status_code == 404


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
