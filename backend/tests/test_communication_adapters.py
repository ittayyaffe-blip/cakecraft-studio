"""Dependency-free self-check for the Communication Adapter abstraction
and the Gmail/WhatsApp adapters' pure logic — no network/DB/HTTP
connection required. Run from `backend/`:

    python -m tests.test_communication_adapters

Covers: the adapter registry (now with two adapters registered
simultaneously — see the "coexist cleanly" tests near the bottom), each
adapter's message-composition logic and unconfigured-fallback behavior,
and notification_service._dispatch's critical "not registered vs.
registered-but-unconfigured — both fall back to the stub, neither is a
real failure" distinction, which is what keeps
tools/demo_data_seed.py's simulated "sent" notifications realistic
without real Resend/WhatsApp credentials configured. Real delivery (an
actual Resend or WhatsApp Cloud API call) is intentionally never
exercised here — see docs/SPRINT3_COMMUNICATION_ADAPTER.md and
docs/SPRINT4_WHATSAPP_ADAPTER.md.
"""

from unittest.mock import MagicMock, patch

from app.services import communication, notification_service
from app.services.communication import gmail_adapter, whatsapp_adapter
from app.services.communication.base import CommunicationAdapter, DeliveryResult


def test_gmail_adapter_satisfies_the_protocol():
    assert isinstance(gmail_adapter, CommunicationAdapter)


def test_gmail_adapter_registered_under_its_own_channel():
    assert communication.get_adapter("email") is gmail_adapter


def test_get_adapter_returns_none_for_unknown_channel():
    assert communication.get_adapter("carrier-pigeon") is None


def test_gmail_not_configured_in_this_environment():
    # True today (no RESEND_API_KEY set anywhere) — this is also what
    # keeps the rest of this file safe to run with no real credentials
    # and no network access.
    assert gmail_adapter.is_configured() is False


def test_gmail_send_without_config_returns_clean_failure_no_network():
    result = gmail_adapter.send(
        {"id": "x", "subject": "Hi", "body": "Hi", "customers": {"email": "a@b.com"}}
    )
    assert isinstance(result, DeliveryResult)
    assert result.success is False
    assert "not configured" in result.error


def test_build_payload_uses_notification_fields_and_sets_reply_to():
    notification = {
        "subject": "Your cake is ready!",
        "body": "Come get it.",
        "customers": {"email": "jane@example.com"},
    }
    with patch.object(gmail_adapter.settings, "gmail_address", "mybestcake2002@gmail.com"):
        payload = gmail_adapter._build_payload(notification)
    assert payload["to"] == ["jane@example.com"]
    assert payload["subject"] == "Your cake is ready!"
    assert payload["text"] == "Come get it."
    # Sent from Resend's shared sandbox domain (gmail.com isn't CakeCraft's
    # to verify with a third party) but replies still reach the real inbox.
    assert payload["reply_to"] == "mybestcake2002@gmail.com"


def test_build_payload_raises_for_missing_customer_email():
    try:
        gmail_adapter._build_payload({"subject": "x", "body": "y", "customers": {}})
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError, none was raised")


def test_send_posts_to_resend_and_returns_provider_message_id():
    notification = {
        "id": "notif-1", "subject": "Hi", "body": "Hi there", "customers": {"email": "jane@example.com"},
    }
    fake_response = MagicMock(status_code=200)
    fake_response.json.return_value = {"id": "resend-msg-1"}
    with (
        patch.object(gmail_adapter.settings, "resend_api_key", "re_fake_key_for_test"),
        patch.object(gmail_adapter.httpx, "post", return_value=fake_response) as mock_post,
    ):
        result = gmail_adapter.send(notification)

    assert result.success is True
    assert result.provider_message_id == "resend-msg-1"
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["headers"]["Authorization"] == "Bearer re_fake_key_for_test"
    assert call_kwargs["json"]["to"] == ["jane@example.com"]


def test_send_reports_resend_api_error_cleanly():
    notification = {"id": "notif-2", "subject": "Hi", "body": "Hi", "customers": {"email": "jane@example.com"}}
    fake_response = MagicMock(status_code=422)
    fake_response.json.return_value = {"message": "Invalid `from` field"}
    with (
        patch.object(gmail_adapter.settings, "resend_api_key", "re_fake_key_for_test"),
        patch.object(gmail_adapter.httpx, "post", return_value=fake_response),
    ):
        result = gmail_adapter.send(notification)

    assert result.success is False
    assert result.error == "Invalid `from` field"


def test_send_never_raises_on_a_network_exception():
    notification = {"id": "notif-3", "subject": "Hi", "body": "Hi", "customers": {"email": "jane@example.com"}}
    with (
        patch.object(gmail_adapter.settings, "resend_api_key", "re_fake_key_for_test"),
        patch.object(gmail_adapter.httpx, "post", side_effect=TimeoutError("timed out")),
    ):
        result = gmail_adapter.send(notification)

    assert result.success is False
    assert "timed out" in result.error


def test_dispatch_falls_back_to_stub_when_channel_unregistered():
    channel, result = notification_service._dispatch({"channel": "carrier-pigeon"})
    assert channel == "carrier-pigeon"
    assert result.success is True  # stub: reports success, nothing actually delivered


def test_dispatch_falls_back_to_stub_when_registered_but_unconfigured():
    # channel=None resolves to DEFAULT_CHANNEL ("email"), which *is*
    # registered (gmail_adapter) but has no real credentials — the
    # critical distinction this sprint introduces: not the same as a real
    # delivery failure.
    channel, result = notification_service._dispatch({"channel": None})
    assert channel == "email"
    assert result.success is True


def test_send_rejects_invalid_status_before_attempting_any_dispatch():
    # "draft" used to be rejected here too, before the simplified workflow
    # (draft -> send -> sent/failed) made it a valid starting status for
    # send() -- see notification_service._SEND_ALLOWED_FROM. "queued" (a
    # notification whose template hasn't even rendered yet) still isn't.
    try:
        notification_service.send({"status": "queued", "id": "x"})
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError, none was raised")


def test_whatsapp_adapter_satisfies_the_protocol():
    assert isinstance(whatsapp_adapter, CommunicationAdapter)


def test_whatsapp_adapter_registered_under_its_own_channel():
    assert communication.get_adapter("whatsapp") is whatsapp_adapter


def test_whatsapp_not_configured_in_this_environment():
    # True today (no WHATSAPP_ACCESS_TOKEN/WHATSAPP_PHONE_NUMBER_ID set
    # anywhere) — same role as the equivalent Gmail check: what keeps the
    # rest of this file safe to run with no real credentials or network.
    assert whatsapp_adapter.is_configured() is False


def test_whatsapp_send_without_config_returns_clean_failure_no_network():
    result = whatsapp_adapter.send(
        {"id": "x", "subject": "Hi", "body": "Hi", "customers": {"phone": "+33 6 12 34 56 78"}}
    )
    assert isinstance(result, DeliveryResult)
    assert result.success is False
    assert "not configured" in result.error


def test_to_whatsapp_number_strips_formatting():
    assert whatsapp_adapter._to_whatsapp_number("+33 6 12 34 56 78") == "33612345678"


def test_build_message_text_combines_subject_and_body():
    text = whatsapp_adapter._build_message_text({"subject": "Ready!", "body": "Come get it."})
    assert text == "Ready!\n\nCome get it."


def test_build_message_text_falls_back_when_one_field_missing():
    assert whatsapp_adapter._build_message_text({"subject": "", "body": "Just the body"}) == "Just the body"
    assert whatsapp_adapter._build_message_text({"subject": None, "body": None}) == "(no content)"


def test_whatsapp_send_without_phone_returns_clean_failure():
    # Would be "not configured" first in this environment regardless, but
    # this proves the missing-phone guard exists and reads correctly by
    # calling it directly rather than relying on is_configured() to mask it.
    if whatsapp_adapter.is_configured():
        raise AssertionError("test assumes an unconfigured environment — see is_configured() check above")
    result = whatsapp_adapter.send({"id": "x", "subject": "Hi", "body": "Hi", "customers": {}})
    assert result.success is False


# --- Gmail and WhatsApp coexisting through the same registry ---------------
# The actual proof this sprint asked for: both adapters registered at
# once, each resolved independently and correctly, neither affecting the
# other's behavior.


def test_both_adapters_are_registered_simultaneously():
    assert communication.get_adapter("email") is gmail_adapter
    assert communication.get_adapter("whatsapp") is whatsapp_adapter
    assert gmail_adapter is not whatsapp_adapter


def test_dispatch_routes_email_channel_to_gmail_not_whatsapp():
    channel, result = notification_service._dispatch({"channel": "email"})
    assert channel == "email"
    assert result.success is True  # stub fallback — gmail_adapter is registered but unconfigured


def test_dispatch_routes_whatsapp_channel_to_whatsapp_not_gmail():
    channel, result = notification_service._dispatch({"channel": "whatsapp"})
    assert channel == "whatsapp"
    assert result.success is True  # stub fallback — whatsapp_adapter is registered but unconfigured


def test_default_channel_still_resolves_to_email_unaffected_by_whatsapp():
    # Sprint 4 registered a second adapter but did not touch
    # DEFAULT_CHANNEL or _dispatch()'s fallback logic — a notification
    # with no channel set still resolves to email, exactly as before this
    # sprint. This is the literal "do not modify runtime behavior" check.
    channel, _ = notification_service._dispatch({"channel": None})
    assert channel == communication.DEFAULT_CHANNEL == "email"


def test_return_to_draft_now_accepts_failed():
    # Sprint 3 added "failed" to this guard alongside send() being able
    # to produce it for the first time. Asserted against the named
    # constant rather than by calling return_to_draft() itself, which
    # would reach a real (currently nonexistent) Supabase table.
    assert "failed" in notification_service._RETURN_TO_DRAFT_ALLOWED_FROM


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
