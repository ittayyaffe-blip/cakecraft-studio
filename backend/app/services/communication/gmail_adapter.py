"""Gmail email adapter — Sprint 3's first concrete CommunicationAdapter.

Sends a notification's already-rendered subject/body to its customer's
email via Gmail SMTP with an app password — not the full Gmail API, per
Master_Blueprint_v1.md §10's own "start simple" recommendation for this
integration. Only Python's standard library is used (`smtplib`, `email`)
— no new dependency, no addition to requirements.txt.

Every other integration point in this project degrades cleanly when
unconfigured (see core/config.py's gmail_address/gmail_app_password); this
adapter is no different: with no credentials set, `is_configured()` is
False and `send()` returns a clean, explicit failure rather than raising
or silently pretending to succeed. `notification_service._dispatch`
treats "not configured" as "fall back to the original stub" rather than a
real delivery failure — see that function's docstring for why.

Module-level `channel`/`is_configured`/`send` — not a class — satisfies
communication.base.CommunicationAdapter structurally; see that module's
docstring for why this project uses plain modules over class hierarchies
here.
"""

import logging
import smtplib
import socket
from email.message import EmailMessage
from email.utils import make_msgid

from app.core.config import settings
from app.services.communication.base import DeliveryResult

logger = logging.getLogger(__name__)

channel = "email"

_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 587
_SMTP_TIMEOUT_SECONDS = 10


class _IPv4SMTP(smtplib.SMTP):
    """Plain smtplib.SMTP resolves smtp.gmail.com via whatever getaddrinfo()
    returns first, which on Railway's containers is its IPv6 (AAAA) address
    -- Railway's network doesn't actually route IPv6 out, so that first
    connection attempt dies immediately with "OSError: [Errno 101] Network
    is unreachable" (confirmed in production logs; every real send attempt
    hit exactly this). Forcing IPv4-only resolution here is the minimal
    fix. TLS hostname verification is unaffected: starttls() still checks
    the certificate against the original hostname passed to __init__, not
    the resolved IP this override connects to.
    """

    def _get_socket(self, host, port, timeout):
        ipv4_addr = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
        return socket.create_connection((ipv4_addr, port), timeout, source_address=self.source_address)


def is_configured() -> bool:
    return bool(settings.gmail_address and settings.gmail_app_password)


def _build_message(notification: dict) -> EmailMessage:
    """Compose the email from a notification's rendered content — a pure
    function (no network, no credentials touched) so it's testable on its
    own; see backend/tests/test_communication_adapters.py.

    Raises ValueError if the notification has no customer email to send
    to — send() below turns that into a DeliveryResult rather than
    letting it propagate.
    """
    customer = notification.get("customers") or {}
    recipient = customer.get("email")
    if not recipient:
        raise ValueError("Notification has no customer email to send to")

    message = EmailMessage()
    message["Subject"] = notification.get("subject") or "(no subject)"
    message["From"] = settings.gmail_address or ""
    message["To"] = recipient
    message.set_content(notification.get("body") or "")
    return message


def send(notification: dict) -> DeliveryResult:
    """Send one notification's subject/body to its customer's email.

    Never raises: a real send failure (bad credentials, SMTP timeout, no
    recipient email) is reported through the returned DeliveryResult, not
    an exception, so notification_service.send() can transition the
    notification to "failed" cleanly instead of the request blowing up.
    """
    if not is_configured():
        return DeliveryResult(
            success=False,
            error="Gmail adapter is not configured (GMAIL_ADDRESS/GMAIL_APP_PASSWORD unset)",
        )

    try:
        message = _build_message(notification)
    except ValueError as exc:
        return DeliveryResult(success=False, error=str(exc))

    message_id = make_msgid()
    message["Message-Id"] = message_id

    try:
        with _IPv4SMTP(_SMTP_HOST, _SMTP_PORT, timeout=_SMTP_TIMEOUT_SECONDS) as smtp:
            smtp.starttls()
            smtp.login(settings.gmail_address, settings.gmail_app_password)
            smtp.send_message(message)
        return DeliveryResult(success=True, provider_message_id=message_id)
    except Exception as exc:
        logger.exception("Gmail send failed for notification=%s", notification.get("id"))
        return DeliveryResult(success=False, error=str(exc))
