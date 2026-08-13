"""Twilio WhatsApp Sandbox inbound — a second, parallel way to reach the
same "whatsapp" channel the Meta Cloud API integration (whatsapp_inbound.py)
already provides, used for this project's university/demo Twilio Sandbox
setup instead of a Meta Business/WhatsApp Business registration. Mirrors
whatsapp_inbound.py's shape (module-level functions, no class) for the
same reasons documented there, but speaks a genuinely different protocol,
not a config variant of the same one:

  - Meta signs the raw JSON body with HMAC-SHA256 (X-Hub-Signature-256).
  - Twilio signs the *full request URL plus every POST param*, sorted and
    concatenated, with HMAC-SHA1 (X-Twilio-Signature), and sends the body
    as application/x-www-form-urlencoded, not JSON.

Security is the whole point of this module, same as whatsapp_inbound.py:
app/api/routes/webhooks_twilio.py exposes a public, unauthenticated URL
(Twilio's servers call it directly), so everything trusting its content
has to be verified here first. One secret does both jobs Meta needed two
for: TWILIO_AUTH_TOKEN both signs outbound Basic Auth (see
twilio_whatsapp_adapter.py) and verifies this inbound signature — there is
no separate "verify token" concept in Twilio's model, and no one-time GET
handshake either (a webhook URL is simply pasted into the Twilio Console's
Sandbox settings, not verified via a challenge-response like Meta's).

Unconfigured (`TWILIO_AUTH_TOKEN` unset) fails closed (returns False), not
open — see is_configured() and the one call site in webhooks_twilio.py.

Signature verification itself delegates to Twilio's own
`twilio.request_validator.RequestValidator` rather than a hand-written
HMAC (an earlier version of this file reimplemented the algorithm
directly — mathematically equivalent for this webhook's actual payload
shape, but Twilio's official guidance is to use the SDK validator so this
stays correct if the webhook's parameter shape ever changes) — nothing
else from the `twilio` package is used anywhere in this project; the
outbound side (twilio_whatsapp_adapter.py) still sends via plain `httpx`,
unchanged.
"""

import logging
from urllib.parse import urlsplit, urlunsplit

from twilio.request_validator import RequestValidator

from app.core.config import settings

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(settings.twilio_account_sid and settings.twilio_auth_token)


def external_url(request_url: str, forwarded_proto: str | None, forwarded_host: str | None = None) -> str:
    """Reconstructs the exact public HTTPS URL Twilio actually called, for
    verify_signature() to check the signature against — not the internal
    URL FastAPI sees.

    Twilio signs the exact URL it POSTs to. Railway's edge terminates TLS
    and forwards the request to this app over plain HTTP internally;
    uvicorn's proxy-header trust only applies to peers in
    `--forwarded-allow-ips` (default `127.0.0.1`, not set for this
    project's start command), so `request.url` as FastAPI sees it reports
    the *internal* scheme (`http`) — never what Twilio actually saw
    (`https`) — and every real signature check would fail closed. Fixed
    here, scoped to just this one call site, rather than by trusting
    X-Forwarded-* globally for the whole app (which would also change
    request.client.host everywhere else).

    Safe even though these headers are client-suppliable on this public,
    unauthenticated route: they only change *which URL string* gets
    checked, never whether checking happens — a forged header still needs
    a signature matching that exact (attacker-chosen) URL, which requires
    knowing TWILIO_AUTH_TOKEN either way. Falls back to `request_url`
    unchanged when a header is absent (e.g. local dev with no proxy in
    front) — deterministic, not a weaker check, since Railway always sets
    these on real traffic.
    """
    parts = urlsplit(request_url)
    scheme = forwarded_proto or parts.scheme
    netloc = forwarded_host or parts.netloc
    return urlunsplit((scheme, netloc, parts.path, parts.query, parts.fragment))


def verify_signature(url: str, params: dict, signature: str | None) -> bool:
    """Verifies the X-Twilio-Signature header Twilio signs every real
    Sandbox webhook POST with, via Twilio's own RequestValidator (HMAC-SHA1
    over the exact request URL plus every POST parameter's key+value in
    sorted-by-key order, base64-encoded). This is the actual security
    boundary: a POST without a valid signature is rejected before its
    params are matched to a customer or handed to the AI Agent — see
    webhooks_twilio.py's route, which calls this before touching the
    parsed payload.

    `url` must be the *exact* URL Twilio itself called (scheme + host +
    path, no query string stripped/added) — see external_url() above,
    which webhooks_twilio.py uses to build this argument correctly behind
    Railway's proxy.
    """
    if not settings.twilio_auth_token or not signature:
        return False

    return RequestValidator(settings.twilio_auth_token).validate(url, params, signature)


def parse_webhook_payload(params: dict) -> dict | None:
    """Extracts the one real inbound *text* message from an (already
    signature-verified) Twilio Sandbox webhook POST's form params, in the
    same shape whatsapp_inbound.parse_webhook_payload's Meta output uses
    (sender_phone/body/message_id/timestamp_epoch) so inbound_service.
    process_inbound_whatsapp needs no changes at all to accept either.

    Returns None (not an empty list) when there's nothing usable —
    Twilio's Sandbox webhook always carries exactly one message per POST,
    never a batch the way Meta's payload can, so there is no multi-message
    case to handle here. `timestamp_epoch` is always None: Twilio's inbound
    webhook doesn't include one (unlike Meta's), and
    process_inbound_whatsapp already treats a missing timestamp as "use
    now" — an existing, already-tested fallback, not a new one.

    Media messages (NumMedia > "0") and anything with no Body are skipped
    — out of scope for this project's grounded-text-reply flow, same
    "text only" scope decision whatsapp_inbound.py already made for Meta.
    """
    from_field = (params.get("From") or "").strip()
    body = (params.get("Body") or "").strip()
    message_id = (params.get("MessageSid") or "").strip()

    if not from_field or not body or not message_id:
        return None

    sender_phone = from_field.removeprefix("whatsapp:")

    return {
        "sender_phone": sender_phone,
        "body": body,
        "message_id": message_id,
        "timestamp_epoch": None,
    }
