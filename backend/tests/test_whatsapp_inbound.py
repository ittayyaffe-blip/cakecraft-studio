"""Dependency-free self-check for whatsapp_inbound.py's webhook
verification and payload parsing — no network required. Run from
`backend/`:

    python -m tests.test_whatsapp_inbound
"""

import hashlib
import hmac
from unittest.mock import patch

from app.core.config import settings
from app.services.communication import whatsapp_inbound

# --- verify_handshake() (GET, one-time webhook URL registration) -----------


def test_verify_handshake_accepts_matching_token_and_subscribe_mode():
    with patch.object(settings, "whatsapp_webhook_verify_token", "secret-token"):
        assert whatsapp_inbound.verify_handshake("subscribe", "secret-token") is True


def test_verify_handshake_rejects_wrong_token():
    with patch.object(settings, "whatsapp_webhook_verify_token", "secret-token"):
        assert whatsapp_inbound.verify_handshake("subscribe", "wrong-token") is False


def test_verify_handshake_rejects_wrong_mode():
    with patch.object(settings, "whatsapp_webhook_verify_token", "secret-token"):
        assert whatsapp_inbound.verify_handshake("unsubscribe", "secret-token") is False


def test_verify_handshake_fails_closed_when_unconfigured():
    with patch.object(settings, "whatsapp_webhook_verify_token", None):
        assert whatsapp_inbound.verify_handshake("subscribe", "anything") is False


# --- verify_signature() (POST, every real inbound webhook call) ------------


def test_verify_signature_accepts_correct_hmac():
    body = b'{"entry": []}'
    with patch.object(settings, "whatsapp_app_secret", "app-secret"):
        expected = "sha256=" + hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()
        assert whatsapp_inbound.verify_signature(body, expected) is True


def test_verify_signature_rejects_tampered_body():
    body = b'{"entry": []}'
    tampered = b'{"entry": [1]}'
    with patch.object(settings, "whatsapp_app_secret", "app-secret"):
        sig = "sha256=" + hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()
        assert whatsapp_inbound.verify_signature(tampered, sig) is False


def test_verify_signature_rejects_wrong_secret():
    body = b'{"entry": []}'
    sig = "sha256=" + hmac.new(b"a-different-secret", body, hashlib.sha256).hexdigest()
    with patch.object(settings, "whatsapp_app_secret", "app-secret"):
        assert whatsapp_inbound.verify_signature(body, sig) is False


def test_verify_signature_fails_closed_when_unconfigured():
    with patch.object(settings, "whatsapp_app_secret", None):
        assert whatsapp_inbound.verify_signature(b"x", "sha256=whatever") is False


def test_verify_signature_rejects_missing_header():
    with patch.object(settings, "whatsapp_app_secret", "app-secret"):
        assert whatsapp_inbound.verify_signature(b"x", None) is False


def test_verify_signature_rejects_malformed_header():
    with patch.object(settings, "whatsapp_app_secret", "app-secret"):
        assert whatsapp_inbound.verify_signature(b"x", "not-a-real-signature") is False


# --- parse_webhook_payload() ------------------------------------------------


def test_parse_webhook_payload_extracts_a_text_message():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "33612345678",
                                    "type": "text",
                                    "text": {"body": "Is my cake ready?"},
                                    "id": "wamid.abc123",
                                    "timestamp": "1699999999",
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    messages = whatsapp_inbound.parse_webhook_payload(payload)
    assert len(messages) == 1
    assert messages[0]["sender_phone"] == "33612345678"
    assert messages[0]["body"] == "Is my cake ready?"
    assert messages[0]["message_id"] == "wamid.abc123"
    assert messages[0]["timestamp_epoch"] == "1699999999"


def test_parse_webhook_payload_skips_non_text_messages():
    payload = {"entry": [{"changes": [{"value": {"messages": [{"from": "1", "type": "image", "id": "x"}]}}]}]}
    assert whatsapp_inbound.parse_webhook_payload(payload) == []


def test_parse_webhook_payload_skips_delivery_status_callbacks():
    # Status-callback payloads have no "messages" key at all.
    payload = {"entry": [{"changes": [{"value": {"statuses": [{"status": "delivered", "id": "wamid.xyz"}]}}]}]}
    assert whatsapp_inbound.parse_webhook_payload(payload) == []


def test_parse_webhook_payload_handles_empty_or_malformed_payload():
    assert whatsapp_inbound.parse_webhook_payload({}) == []
    assert whatsapp_inbound.parse_webhook_payload({"entry": []}) == []


def test_parse_webhook_payload_extracts_multiple_messages_in_one_call():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {"from": "1", "type": "text", "text": {"body": "First"}, "id": "wamid.1"},
                                {"from": "2", "type": "text", "text": {"body": "Second"}, "id": "wamid.2"},
                            ]
                        }
                    }
                ]
            }
        ]
    }
    messages = whatsapp_inbound.parse_webhook_payload(payload)
    assert len(messages) == 2
    assert {m["message_id"] for m in messages} == {"wamid.1", "wamid.2"}


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
