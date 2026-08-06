"""WhatsApp Business Cloud API adapter — Sprint 4's second concrete
CommunicationAdapter, mirroring gmail_adapter.py's shape exactly (module-
level `channel` / `is_configured()` / `send()`, same DeliveryResult
contract, same "never raises" rule).

Sends a notification's rendered subject/body as a WhatsApp text message
to its customer's phone number via Meta's WhatsApp Business Cloud API — a
plain JSON REST API, not a WhatsApp SDK, per Master_Blueprint_v1.md §10's
"outbound notifications only" scope for this integration. Uses `httpx`,
already an installed, pinned dependency (`requirements.txt` — pulled in
today as supabase-py's own HTTP client); this adapter is simply the first
place application code imports it directly rather than only relying on it
indirectly through supabase-py. No new dependency was added.

Same "gracefully degrades to off" contract as gmail_adapter.py: with no
WHATSAPP_ACCESS_TOKEN/WHATSAPP_PHONE_NUMBER_ID configured,
is_configured() is False and send() returns a clean, explicit failure —
never raises, never pretends to succeed, and — critically —
notification_service._dispatch() treats that the same as "no adapter
registered at all," not a real delivery failure (see that function's
docstring).

Known production limitation, documented rather than worked around: Meta
requires a pre-approved message *template* for business-initiated
messages sent outside a 24-hour customer-service window. This adapter
sends a free-form "text" message — the simplest shape, matching
gmail_adapter.py's own "start simple" scope, and the only shape that can
be implemented and tested without first registering templates with Meta
(an external, manual step, not a code change). See
docs/SPRINT4_WHATSAPP_ADAPTER.md "Future extension points".
"""

import logging
import re

import httpx

from app.core.config import settings
from app.services.communication.base import DeliveryResult

logger = logging.getLogger(__name__)

channel = "whatsapp"

_API_VERSION = "v21.0"
_TIMEOUT_SECONDS = 10


def is_configured() -> bool:
    return bool(settings.whatsapp_access_token and settings.whatsapp_phone_number_id)


def _to_whatsapp_number(phone: str) -> str:
    """Meta's Cloud API expects a recipient as digits only, with country
    code, no leading '+', spaces, or punctuation — e.g. "33612345678" for
    the "+33 6 12 34 56 78" format this project's customers.phone values
    already use (see tools/demo_data_seed.py). A pure function, no
    network — testable on its own.
    """
    return re.sub(r"\D", "", phone)


def _build_message_text(notification: dict) -> str:
    """WhatsApp has no separate subject line — fold the notification's
    subject and body into one message the way a person would actually
    text it. Pure function, no network — testable on its own.
    """
    subject = (notification.get("subject") or "").strip()
    body = (notification.get("body") or "").strip()
    if subject and body:
        return f"{subject}\n\n{body}"
    return subject or body or "(no content)"


def send(notification: dict) -> DeliveryResult:
    """Send one notification's subject/body as a WhatsApp text message to
    its customer's phone number.

    Never raises: a real send failure (bad phone number, invalid/expired
    token, an error Meta's API returns, a timeout) is reported through the
    returned DeliveryResult, not an exception — same contract as
    gmail_adapter.send().
    """
    if not is_configured():
        return DeliveryResult(
            success=False,
            error="WhatsApp adapter is not configured (WHATSAPP_ACCESS_TOKEN/WHATSAPP_PHONE_NUMBER_ID unset)",
        )

    customer = notification.get("customers") or {}
    phone = customer.get("phone")
    if not phone:
        return DeliveryResult(success=False, error="Notification has no customer phone number to send to")

    recipient = _to_whatsapp_number(phone)
    if not recipient:
        return DeliveryResult(
            success=False, error=f"Customer phone number '{phone}' has no digits to send to"
        )

    url = f"https://graph.facebook.com/{_API_VERSION}/{settings.whatsapp_phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "text",
        "text": {"body": _build_message_text(notification)},
    }
    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}

    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=_TIMEOUT_SECONDS)
        data = response.json()
    except Exception as exc:
        logger.exception("WhatsApp send failed for notification=%s", notification.get("id"))
        return DeliveryResult(success=False, error=str(exc))

    if response.status_code >= 400:
        error_message = (data.get("error") or {}).get("message", f"HTTP {response.status_code}")
        logger.error("WhatsApp API rejected notification=%s: %s", notification.get("id"), error_message)
        return DeliveryResult(success=False, error=error_message)

    messages = data.get("messages") or []
    message_id = messages[0].get("id") if messages else None
    return DeliveryResult(success=True, provider_message_id=message_id)
