"""Dependency-free self-check for admin/notifications.py's list route --
specifically the `?channel=` filter's validation, which used to derive
validity from `communication.get_adapter(channel) is not None`. That
wrongly rejected `channel=chat` with a 400: "chat" is a real value
notifications.channel holds (a live-chat answer that already reached the
customer -- see agent_service._insert_chat_answer) but deliberately has
no registered CommunicationAdapter (nothing left to dispatch). Fixed by
validating against notification_service.VALID_CHANNELS instead -- this
file pins that fix. Run from `backend/`:

    python -m tests.test_admin_notifications_route
"""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api.routes.admin import notifications
from app.services.auth_service import AdminIdentity

_ADMIN = AdminIdentity(id="staff-1", email="baker@maisondegateau.fr", role="admin", access_token="t")
_EMPTY_PAGE = {"items": [], "total": 0, "page": 1, "pageSize": 20}


def test_chat_channel_filter_is_accepted_not_400():
    with patch.object(notifications.notification_service, "list_notifications", return_value=_EMPTY_PAGE) as mock_list:
        result = notifications.list_notifications(channel="chat", admin=_ADMIN)

    assert result == _EMPTY_PAGE
    assert mock_list.call_args.kwargs["channel"] == "chat"


def test_email_and_whatsapp_channel_filters_still_accepted():
    with patch.object(notifications.notification_service, "list_notifications", return_value=_EMPTY_PAGE):
        notifications.list_notifications(channel="email", admin=_ADMIN)
        notifications.list_notifications(channel="whatsapp", admin=_ADMIN)
    # No HTTPException raised for either -- the assertion is that this line is reached.


def test_unknown_channel_still_rejected_with_400():
    with pytest.raises(HTTPException) as exc_info:
        notifications.list_notifications(channel="sms", admin=_ADMIN)
    assert exc_info.value.status_code == 400


def test_no_channel_filter_is_still_valid():
    with patch.object(notifications.notification_service, "list_notifications", return_value=_EMPTY_PAGE) as mock_list:
        notifications.list_notifications(channel=None, admin=_ADMIN)
    mock_list.assert_called_once()


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
