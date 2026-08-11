"""Email adapter — Sprint 3's first concrete CommunicationAdapter, sending
via Resend's HTTPS API.

Originally raw SMTP (smtplib + a Gmail app password); switched to Resend
(https://resend.com) after confirming live that Railway blocks outbound
SMTP entirely at the network level — direct in-container testing showed
ports 25/465/587/2525 to smtp.gmail.com all silently time out, while
HTTPS egress works instantly, so no SMTP-side code (IPv4 forcing, retries,
alternate ports) could ever have delivered mail from this host. Resend
sends over HTTPS, the same transport every other outbound integration in
this project (whatsapp_adapter.py, the Anthropic/Supabase clients)
already uses successfully. Uses `httpx`, already an installed, pinned
dependency — no new one added.

Sends From Resend's own shared sandbox address (onboarding@resend.dev),
not mybestcake2002@gmail.com: a third-party provider can only send as a
domain *you've* verified via DNS, and gmail.com is Google's domain, not
CakeCraft's — there's nothing to verify. Reply-To is set to the real
business Gmail address (GMAIL_ADDRESS) so customer replies still land in
the right inbox. `_FROM_ADDRESS` is the one line to change if/when
CakeCraft verifies its own sending domain with Resend.

Every other integration point in this project degrades cleanly when
unconfigured (see core/config.py's resend_api_key); this adapter is no
different: with no API key set, `is_configured()` is False and `send()`
returns a clean, explicit failure rather than raising or silently
pretending to succeed. `notification_service._dispatch` treats "not
configured" as "fall back to the original stub" rather than a real
delivery failure — see that function's docstring.

Module-level `channel`/`is_configured`/`send` — not a class — satisfies
communication.base.CommunicationAdapter structurally; see that module's
docstring for why this project uses plain modules over class hierarchies
here.
"""

import logging

import httpx

from app.core.config import settings
from app.services.communication.base import DeliveryResult

logger = logging.getLogger(__name__)

channel = "email"

_RESEND_URL = "https://api.resend.com/emails"
_TIMEOUT_SECONDS = 10
_FROM_ADDRESS = "CakeCraft Studio / Maison de Gâteau Paris <onboarding@resend.dev>"


def is_configured() -> bool:
    return bool(settings.resend_api_key)


def _build_payload(notification: dict) -> dict:
    """Compose the Resend API request body from a notification's rendered
    content — a pure function (no network, no credentials touched) so
    it's testable on its own; see backend/tests/test_communication_adapters.py.

    Raises ValueError if the notification has no customer email to send
    to — send() below turns that into a DeliveryResult rather than
    letting it propagate.
    """
    customer = notification.get("customers") or {}
    recipient = customer.get("email")
    if not recipient:
        raise ValueError("Notification has no customer email to send to")

    payload = {
        "from": _FROM_ADDRESS,
        "to": [recipient],
        "subject": notification.get("subject") or "(no subject)",
        "text": notification.get("body") or "",
    }
    if settings.gmail_address:
        payload["reply_to"] = settings.gmail_address
    return payload


def send(notification: dict) -> DeliveryResult:
    """Send one notification's subject/body to its customer's email via
    Resend's HTTPS API.

    Never raises: a real send failure (bad recipient, invalid/expired API
    key, an error Resend's API returns, a timeout) is reported through
    the returned DeliveryResult, not an exception, so
    notification_service.send() can transition the notification to
    "failed" cleanly instead of the request blowing up.
    """
    if not is_configured():
        return DeliveryResult(
            success=False,
            error="Resend adapter is not configured (RESEND_API_KEY unset)",
        )

    try:
        payload = _build_payload(notification)
    except ValueError as exc:
        return DeliveryResult(success=False, error=str(exc))

    headers = {"Authorization": f"Bearer {settings.resend_api_key}"}

    try:
        response = httpx.post(_RESEND_URL, json=payload, headers=headers, timeout=_TIMEOUT_SECONDS)
        data = response.json()
    except Exception as exc:
        logger.exception("Resend send failed for notification=%s", notification.get("id"))
        return DeliveryResult(success=False, error=str(exc))

    if response.status_code >= 400:
        error_message = data.get("message") or f"HTTP {response.status_code}"
        logger.error("Resend API rejected notification=%s: %s", notification.get("id"), error_message)
        return DeliveryResult(success=False, error=error_message)

    return DeliveryResult(success=True, provider_message_id=data.get("id"))
