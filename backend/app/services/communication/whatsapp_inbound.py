"""WhatsApp inbound — Step 3's Meta Cloud API webhook mechanics: the
one-time verification handshake, request-signature validation, and
payload parsing. Mirrors whatsapp_adapter.py's shape (module-level
functions, no class) for the same reasons documented there.

Security is the whole point of this module: app/api/routes/webhooks.py
exposes a public, unauthenticated URL (Meta's servers call it directly —
there's no admin session to check), so everything trusting its content
has to be verified here first. Two independent secrets, two different
jobs:

  - whatsapp_webhook_verify_token — proves whoever configured the webhook
    URL in the Meta dashboard is us, checked once, at setup time (the GET
    handshake).
  - whatsapp_app_secret — proves each individual POST actually came from
    Meta, checked on every request, via HMAC-SHA256 over the raw body
    (the X-Hub-Signature-256 header).

Both unset means both checks fail closed (return False), not open — see
is_configured() and every call site in webhooks.py.
"""

import hashlib
import hmac
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(settings.whatsapp_app_secret and settings.whatsapp_webhook_verify_token)


def verify_handshake(mode: str | None, token: str | None) -> bool:
    """Meta's one-time GET verification when a webhook URL is registered
    in the Meta App Dashboard: it sends hub.mode=subscribe and
    hub.verify_token=<whatever we told it to expect>; echoing back
    hub.challenge is what confirms the URL to Meta. hmac.compare_digest
    avoids a timing side-channel on the token comparison, same reasoning
    as verify_signature below.
    """
    if mode != "subscribe" or not token or not settings.whatsapp_webhook_verify_token:
        return False
    return hmac.compare_digest(token, settings.whatsapp_webhook_verify_token)


def verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """Verifies the X-Hub-Signature-256 header Meta signs every real
    webhook POST with (HMAC-SHA256 over the exact raw request body, keyed
    with the Meta App Secret). This is the actual security boundary: a
    POST without a valid signature is rejected before its JSON is even
    parsed, let alone matched to a customer or handed to the AI Agent —
    see webhooks.py's route, which calls this before touching the body.
    """
    if not settings.whatsapp_app_secret or not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(settings.whatsapp_app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, provided)


def parse_webhook_payload(payload: dict) -> list[dict]:
    """Extracts every real inbound *text* message from one (already
    signature-verified) Meta webhook POST body. Pure function, no
    network — testable directly against a constructed payload dict.

    A single webhook call can carry more than one message, and the same
    payload shape also carries delivery-status callbacks (sent/delivered/
    read receipts for messages *we* sent) mixed into `changes` — those
    are silently skipped here (no `messages` key to find), not treated as
    errors; Step 3 doesn't act on delivery receipts yet (the same reason
    notifications.status's "delivered" value is still unused). Non-text
    messages (image/audio/location/...) are skipped too — out of scope
    for Step 3's grounded-text-reply flow.
    """
    messages = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []):
                if msg.get("type") != "text":
                    continue
                messages.append(
                    {
                        "sender_phone": msg.get("from"),
                        "body": (msg.get("text") or {}).get("body", ""),
                        "message_id": msg.get("id"),
                        "timestamp_epoch": msg.get("timestamp"),
                    }
                )
    return messages
