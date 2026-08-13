"""Real-HTTP coverage for webhooks_twilio.py's POST route itself.

test_twilio_whatsapp_inbound.py thoroughly covers verify_signature(),
external_url(), and parse_webhook_payload() as pure functions, but never
exercises the route handler through actual request parsing. That gap let a
real bug through: `await request.form()` needs python-multipart installed
(Starlette requires it for *any* form parsing, including plain urlencoded
bodies, not just multipart), and it wasn't declared as a dependency --
every real Twilio webhook call would have 500'd in production. Caught by
booting the app and POSTing to it for real; this test pins that fix so it
can't silently regress.

The tests below also reproduce Railway's exact deployment shape end to
end: TestClient's requests arrive as http://testserver/... (matching
Railway's internal, post-TLS-termination hop), with X-Forwarded-Proto/
X-Forwarded-Host set the way Railway's edge sets them on real traffic --
proving the route, not just external_url() in isolation, does the right
thing with them.
"""

import base64
import hashlib
import hmac
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app)
_URL = "http://testserver/webhooks/twilio-whatsapp"


def _sign(url: str, params: dict, auth_token: str) -> str:
    data = url + "".join(f"{key}{params[key]}" for key in sorted(params))
    return base64.b64encode(hmac.new(auth_token.encode(), data.encode("utf-8"), hashlib.sha1).digest()).decode()


def test_missing_signature_is_rejected_without_500():
    response = client.post(
        "/webhooks/twilio-whatsapp",
        data={"From": "whatsapp:+33612345678", "Body": "hi", "MessageSid": "SM1"},
    )
    assert response.status_code == 403


def test_valid_signature_is_accepted_and_returns_empty_twiml():
    params = {"From": "whatsapp:+33612345678", "Body": "Is my cake ready?", "MessageSid": "SM123"}
    with (
        patch.object(settings, "twilio_auth_token", "auth-token"),
        patch("app.api.routes.webhooks_twilio.inbound_service.process_inbound_whatsapp") as mock_process,
    ):
        signature = _sign(_URL, params, "auth-token")
        response = client.post(
            "/webhooks/twilio-whatsapp",
            data=params,
            headers={"X-Twilio-Signature": signature},
        )
    assert response.status_code == 200
    assert response.text == "<Response></Response>"
    mock_process.assert_called_once()


# --- Railway reverse-proxy URL reconstruction, end to end -------------------


def test_railway_style_http_internal_plus_forwarded_https_validates():
    """The actual deployed shape: request arrives as http://testserver/...
    (Railway's internal hop) but Twilio signed the https:// URL its own
    edge advertises via X-Forwarded-Proto -- must still validate."""
    params = {"From": "whatsapp:+33612345678", "Body": "Is my cake ready?", "MessageSid": "SM123"}
    external = "https://testserver/webhooks/twilio-whatsapp"
    with (
        patch.object(settings, "twilio_auth_token", "auth-token"),
        patch("app.api.routes.webhooks_twilio.inbound_service.process_inbound_whatsapp"),
    ):
        signature = _sign(external, params, "auth-token")
        response = client.post(
            "/webhooks/twilio-whatsapp",
            data=params,
            headers={"X-Twilio-Signature": signature, "X-Forwarded-Proto": "https"},
        )
    assert response.status_code == 200


def test_forwarded_host_is_honored():
    """Twilio's Console has the public Railway domain configured -- prove
    the route validates against that domain, not TestClient's internal
    'testserver' host, when X-Forwarded-Host says so."""
    params = {"From": "whatsapp:+33612345678", "Body": "hi", "MessageSid": "SM1"}
    external = "https://web-production-c9dd99.up.railway.app/webhooks/twilio-whatsapp"
    with (
        patch.object(settings, "twilio_auth_token", "auth-token"),
        patch("app.api.routes.webhooks_twilio.inbound_service.process_inbound_whatsapp"),
    ):
        signature = _sign(external, params, "auth-token")
        response = client.post(
            "/webhooks/twilio-whatsapp",
            data=params,
            headers={
                "X-Twilio-Signature": signature,
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "web-production-c9dd99.up.railway.app",
            },
        )
    assert response.status_code == 200


def test_tampered_forwarded_proto_fails_closed():
    """Signature was computed for https, but the request claims http via
    X-Forwarded-Proto -- must not validate."""
    params = {"From": "whatsapp:+33612345678", "Body": "hi", "MessageSid": "SM1"}
    signed_for = "https://testserver/webhooks/twilio-whatsapp"
    with patch.object(settings, "twilio_auth_token", "auth-token"):
        signature = _sign(signed_for, params, "auth-token")
        response = client.post(
            "/webhooks/twilio-whatsapp",
            data=params,
            headers={"X-Twilio-Signature": signature, "X-Forwarded-Proto": "http"},
        )
    assert response.status_code == 403


def test_tampered_forwarded_host_fails_closed():
    """Signature was computed for the real Railway domain, but the request
    claims a different host via X-Forwarded-Host -- must not validate."""
    params = {"From": "whatsapp:+33612345678", "Body": "hi", "MessageSid": "SM1"}
    signed_for = "https://web-production-c9dd99.up.railway.app/webhooks/twilio-whatsapp"
    with patch.object(settings, "twilio_auth_token", "auth-token"):
        signature = _sign(signed_for, params, "auth-token")
        response = client.post(
            "/webhooks/twilio-whatsapp",
            data=params,
            headers={
                "X-Twilio-Signature": signature,
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "evil.example.com",
            },
        )
    assert response.status_code == 403


def test_tampered_signature_fails_closed_even_with_correct_url():
    params = {"From": "whatsapp:+33612345678", "Body": "hi", "MessageSid": "SM1"}
    with patch.object(settings, "twilio_auth_token", "auth-token"):
        response = client.post(
            "/webhooks/twilio-whatsapp",
            data=params,
            headers={"X-Twilio-Signature": "not-a-real-signature", "X-Forwarded-Proto": "https"},
        )
    assert response.status_code == 403


def test_missing_forwarded_headers_fall_back_to_raw_request_url():
    """No proxy in front at all (e.g. local dev, or curl hitting the app
    directly) -- must still validate against the exact URL the request
    actually arrived on, deterministically, not fail or guess."""
    params = {"From": "whatsapp:+33612345678", "Body": "hi", "MessageSid": "SM1"}
    with (
        patch.object(settings, "twilio_auth_token", "auth-token"),
        patch("app.api.routes.webhooks_twilio.inbound_service.process_inbound_whatsapp"),
    ):
        signature = _sign(_URL, params, "auth-token")
        response = client.post(
            "/webhooks/twilio-whatsapp",
            data=params,
            headers={"X-Twilio-Signature": signature},
        )
    assert response.status_code == 200


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")
