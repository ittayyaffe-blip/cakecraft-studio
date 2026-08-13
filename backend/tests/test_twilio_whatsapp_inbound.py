"""Dependency-free self-check for twilio_whatsapp_inbound.py's webhook
verification and payload parsing — no network required. Run from
`backend/`:

    python -m tests.test_twilio_whatsapp_inbound

Mirrors test_whatsapp_inbound.py's structure exactly, but for Twilio's
own signature algorithm (HMAC-SHA1 over URL+sorted-params, base64) and
form-shaped (not nested-JSON) payload.
"""

import base64
import hashlib
import hmac
from unittest.mock import patch

from app.core.config import settings
from app.services.communication import twilio_whatsapp_inbound

_URL = "https://web-production-c9dd99.up.railway.app/webhooks/twilio-whatsapp"


def _sign(url: str, params: dict, auth_token: str) -> str:
    """Test-only reimplementation of Twilio's signing algorithm, kept
    deliberately independent of twilio_whatsapp_inbound.verify_signature's
    own implementation (not imported from it) -- if the production
    algorithm were ever accidentally changed to something that no longer
    matches Twilio's real spec, a test that re-derives the expected value
    the same way the code under test does would never catch that.
    """
    data = url + "".join(f"{key}{params[key]}" for key in sorted(params))
    return base64.b64encode(hmac.new(auth_token.encode(), data.encode("utf-8"), hashlib.sha1).digest()).decode()


# --- verify_signature() (POST, every real inbound Sandbox webhook call) ----


def test_verify_signature_accepts_correct_hmac():
    params = {"From": "whatsapp:+33612345678", "Body": "Is my cake ready?", "MessageSid": "SM123"}
    with patch.object(settings, "twilio_auth_token", "auth-token"):
        signature = _sign(_URL, params, "auth-token")
        assert twilio_whatsapp_inbound.verify_signature(_URL, params, signature) is True


def test_verify_signature_rejects_tampered_params():
    params = {"From": "whatsapp:+33612345678", "Body": "Is my cake ready?", "MessageSid": "SM123"}
    with patch.object(settings, "twilio_auth_token", "auth-token"):
        signature = _sign(_URL, params, "auth-token")
        tampered = {**params, "Body": "Give me a free cake"}
        assert twilio_whatsapp_inbound.verify_signature(_URL, tampered, signature) is False


def test_verify_signature_rejects_tampered_url():
    params = {"From": "whatsapp:+33612345678", "Body": "Is my cake ready?", "MessageSid": "SM123"}
    with patch.object(settings, "twilio_auth_token", "auth-token"):
        signature = _sign(_URL, params, "auth-token")
        assert twilio_whatsapp_inbound.verify_signature(_URL + "/evil", params, signature) is False


def test_verify_signature_rejects_wrong_auth_token():
    params = {"From": "whatsapp:+33612345678", "Body": "Is my cake ready?", "MessageSid": "SM123"}
    signature = _sign(_URL, params, "a-different-token")
    with patch.object(settings, "twilio_auth_token", "auth-token"):
        assert twilio_whatsapp_inbound.verify_signature(_URL, params, signature) is False


def test_verify_signature_fails_closed_when_unconfigured():
    params = {"From": "whatsapp:+1", "Body": "x", "MessageSid": "SM1"}
    with patch.object(settings, "twilio_auth_token", None):
        assert twilio_whatsapp_inbound.verify_signature(_URL, params, "anything") is False


def test_verify_signature_rejects_missing_signature():
    params = {"From": "whatsapp:+1", "Body": "x", "MessageSid": "SM1"}
    with patch.object(settings, "twilio_auth_token", "auth-token"):
        assert twilio_whatsapp_inbound.verify_signature(_URL, params, None) is False


def test_verify_signature_rejects_malformed_signature():
    params = {"From": "whatsapp:+1", "Body": "x", "MessageSid": "SM1"}
    with patch.object(settings, "twilio_auth_token", "auth-token"):
        assert twilio_whatsapp_inbound.verify_signature(_URL, params, "not-a-real-signature") is False


# --- external_url() (Railway TLS-termination fix) ---------------------------


def test_external_url_corrects_scheme_from_forwarded_proto():
    result = twilio_whatsapp_inbound.external_url(
        "http://web-production-c9dd99.up.railway.app/webhooks/twilio-whatsapp", "https", None
    )
    assert result == "https://web-production-c9dd99.up.railway.app/webhooks/twilio-whatsapp"


def test_external_url_uses_forwarded_host_when_present():
    result = twilio_whatsapp_inbound.external_url(
        "http://internal-hostname/webhooks/twilio-whatsapp", "https", "web-production-c9dd99.up.railway.app"
    )
    assert result == "https://web-production-c9dd99.up.railway.app/webhooks/twilio-whatsapp"


def test_external_url_falls_back_to_original_when_headers_absent():
    original = "http://127.0.0.1:8000/webhooks/twilio-whatsapp"
    assert twilio_whatsapp_inbound.external_url(original, None, None) == original


def test_external_url_preserves_path_and_query():
    result = twilio_whatsapp_inbound.external_url(
        "http://internal/webhooks/twilio-whatsapp?foo=bar", "https", "public.example.com"
    )
    assert result == "https://public.example.com/webhooks/twilio-whatsapp?foo=bar"


# --- is_configured() --------------------------------------------------------


def test_is_configured_requires_both_sid_and_token():
    with (
        patch.object(settings, "twilio_account_sid", "AC123"),
        patch.object(settings, "twilio_auth_token", "auth-token"),
    ):
        assert twilio_whatsapp_inbound.is_configured() is True

    with (
        patch.object(settings, "twilio_account_sid", "AC123"),
        patch.object(settings, "twilio_auth_token", None),
    ):
        assert twilio_whatsapp_inbound.is_configured() is False


# --- parse_webhook_payload() ------------------------------------------------


def test_parse_webhook_payload_extracts_a_text_message():
    params = {"From": "whatsapp:+33612345678", "To": "whatsapp:+14155238886", "Body": "Is my cake ready?", "MessageSid": "SM123abc"}
    parsed = twilio_whatsapp_inbound.parse_webhook_payload(params)
    assert parsed == {
        "sender_phone": "+33612345678",
        "body": "Is my cake ready?",
        "message_id": "SM123abc",
        "timestamp_epoch": None,
    }


def test_parse_webhook_payload_strips_the_whatsapp_prefix_from_sender():
    params = {"From": "whatsapp:+33612345678", "Body": "Hi", "MessageSid": "SM1"}
    parsed = twilio_whatsapp_inbound.parse_webhook_payload(params)
    assert "whatsapp:" not in parsed["sender_phone"]


def test_parse_webhook_payload_returns_none_for_missing_body():
    params = {"From": "whatsapp:+33612345678", "Body": "", "MessageSid": "SM1"}
    assert twilio_whatsapp_inbound.parse_webhook_payload(params) is None


def test_parse_webhook_payload_returns_none_for_missing_from():
    params = {"Body": "Hi", "MessageSid": "SM1"}
    assert twilio_whatsapp_inbound.parse_webhook_payload(params) is None


def test_parse_webhook_payload_returns_none_for_missing_message_sid():
    params = {"From": "whatsapp:+33612345678", "Body": "Hi"}
    assert twilio_whatsapp_inbound.parse_webhook_payload(params) is None


def test_parse_webhook_payload_returns_none_for_empty_payload():
    assert twilio_whatsapp_inbound.parse_webhook_payload({}) is None


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
