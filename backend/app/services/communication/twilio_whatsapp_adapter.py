"""Twilio WhatsApp Sandbox adapter — a second, parallel CommunicationAdapter
occupying the same "whatsapp" channel whatsapp_adapter.py (Meta) already
implements, for this project's university/demo Twilio Sandbox setup. See
communication/__init__.py for which of the two actually gets registered.

Sends via Twilio's Messages REST API — a plain HTTP form-POST, not a
Twilio SDK — mirroring gmail_adapter.py/whatsapp_adapter.py's shape
exactly (module-level `channel`/`is_configured()`/`send()`, same
DeliveryResult contract, same "never raises" rule, same `httpx` reuse —
already an installed, pinned dependency, no new one added). Twilio's own
Python SDK was deliberately not added: the Messages API is one HTTP POST
with Basic Auth, exactly the same shape every other adapter in this
project already hand-rolls, so a whole new dependency would buy nothing a
few lines of httpx don't already do more consistently with the rest of
this codebase.

Same "gracefully degrades to off" contract as every other adapter: with
no TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN configured, is_configured() is
False and send() returns a clean, explicit failure — never raises, never
pretends to succeed — and notification_service._dispatch() treats that
identically to "no adapter registered at all" (see that function's
docstring).

The Sandbox's shared "from" number (+14155238886) is the same for every
Twilio developer using the free WhatsApp Sandbox — not a secret, not
per-account, so it's a plain constant here rather than a new environment
variable (this project already has explicit "don't add unnecessary
secrets" scope). It would only need to become a real setting if this
project ever moved off the free Sandbox to a paid, dedicated Twilio
WhatsApp Business number — out of scope for this university project.
"""

import logging
import re

import httpx

from app.core.config import settings
from app.services.communication.base import DeliveryResult

logger = logging.getLogger(__name__)

channel = "whatsapp"

_API_BASE = "https://api.twilio.com/2010-04-01"
_TIMEOUT_SECONDS = 10

# The Twilio WhatsApp Sandbox's one shared number, documented publicly by
# Twilio and identical for every developer's free Sandbox — see this
# module's own docstring for why this is a constant, not a setting.
SANDBOX_FROM_NUMBER = "whatsapp:+14155238886"


def is_configured() -> bool:
    return bool(settings.twilio_account_sid and settings.twilio_auth_token)


def _to_whatsapp_address(phone: str) -> str:
    """Twilio's Messages API expects `whatsapp:+<E.164 number>` — digits
    plus a leading `+`, unlike Meta's Cloud API (digits only, no `+`; see
    whatsapp_adapter._to_whatsapp_number). Not reusable verbatim between
    the two adapters for that reason: same normalization *idea*, different
    target format. A pure function, no network — testable on its own.

    One specific, narrow normalization on top of the plain digit-strip:
    a customer phone stored in local Israeli mobile format (`05XXXXXXXX`,
    10 digits, no country code — how a website form naturally captures
    it) has no country code for Twilio to use, so `_to_whatsapp_address`
    would otherwise build an invalid address (`+0...`) — found via the
    real Twilio WhatsApp diagnostic, see tools/test_twilio_whatsapp.py's
    own notes. Rewritten to `972` + the number without its leading `0`
    (E.164), matching this project's actual customer base. Anything else
    — already-international numbers (`+972...`, `972...`, or any other
    country), already correct — passes through unchanged, exactly as
    before this fix; only the one specific 10-digit-starting-with-05
    shape is rewritten.
    """
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return ""
    if digits.startswith("05") and len(digits) == 10:
        digits = "972" + digits[1:]
    return f"whatsapp:+{digits}"


def _build_message_text(notification: dict) -> str:
    """Same "no separate subject line" folding whatsapp_adapter.py already
    does — WhatsApp has no subject field regardless of which provider
    relays it. Pure function, no network — testable on its own.
    """
    subject = (notification.get("subject") or "").strip()
    body = (notification.get("body") or "").strip()
    if subject and body:
        return f"{subject}\n\n{body}"
    return subject or body or "(no content)"


def send(notification: dict) -> DeliveryResult:
    """Send one notification's subject/body as a WhatsApp text message,
    via the Twilio Sandbox, to its customer's phone number.

    Never raises: a real send failure (bad recipient, invalid credentials,
    an error Twilio's API returns, a timeout, or the recipient never
    having joined the Sandbox — a real, common Sandbox-specific failure
    mode) is reported through the returned DeliveryResult, not an
    exception — same contract as every other adapter's send().
    """
    if not is_configured():
        return DeliveryResult(
            success=False,
            error="Twilio adapter is not configured (TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN unset)",
        )

    customer = notification.get("customers") or {}
    phone = customer.get("phone")
    if not phone:
        return DeliveryResult(success=False, error="Notification has no customer phone number to send to")

    recipient = _to_whatsapp_address(phone)
    if not recipient:
        return DeliveryResult(
            success=False, error=f"Customer phone number '{phone}' has no digits to send to"
        )

    url = f"{_API_BASE}/Accounts/{settings.twilio_account_sid}/Messages.json"
    payload = {
        "From": SANDBOX_FROM_NUMBER,
        "To": recipient,
        "Body": _build_message_text(notification),
    }

    try:
        response = httpx.post(
            url,
            data=payload,
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            timeout=_TIMEOUT_SECONDS,
        )
        data = response.json()
    except Exception as exc:
        logger.exception("Twilio WhatsApp send failed for notification=%s", notification.get("id"))
        return DeliveryResult(success=False, error=str(exc))

    if response.status_code >= 400:
        error_message = data.get("message") or f"HTTP {response.status_code}"
        logger.error("Twilio API rejected notification=%s: %s", notification.get("id"), error_message)
        return DeliveryResult(success=False, error=error_message)

    return DeliveryResult(success=True, provider_message_id=data.get("sid"))
