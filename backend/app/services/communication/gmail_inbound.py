"""Gmail inbound — Step 3's mechanism for receiving customer email.

`gmail_adapter.py` can only *send*: SMTP has no concept of receiving.
This module polls the same Gmail account over IMAP instead — a Gmail App
Password (already generated in Step 1 for GMAIL_APP_PASSWORD) authorizes
IMAP access exactly as it does SMTP, so this needs zero new Google-side
setup, zero new credentials, and zero new dependency: `imaplib`/`email`
are Python stdlib, the same `email` package gmail_adapter.py already uses
to *build* messages is used here to *parse* them.

This is the deliberately smallest reliable inbound mechanism for this
project's scale, not the only possible one. The real alternative — Gmail
API push notifications via Google Cloud Pub/Sub — needs a GCP project,
a Pub/Sub topic, domain-wide delegation or OAuth consent, and a public
push-subscription endpoint: real infrastructure for a capstone project
polling one mailbox. IMAP polling trades "instant" for "checked on a
short interval" (see the background poll loop registered in main.py, plus
the manual POST /admin/communications/check-email trigger for on-demand
checks) — an explicit, documented tradeoff, not an oversight.

Captures only what inbound_service.py actually needs (sender, subject,
body, Message-Id, threading refs, received time) — not attachments, not
CC/BCC, not the full raw MIME tree — per the migration's own note on
avoiding unnecessary sensitive email metadata.
"""

import email
import imaplib
import logging
import re
from datetime import datetime, timezone
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime

from app.core.config import settings

logger = logging.getLogger(__name__)

_IMAP_HOST = "imap.gmail.com"
_IMAP_PORT = 993
_MAILBOX = "INBOX"
_HTML_TAG_RE = re.compile(r"<[^<]+?>")


def is_configured() -> bool:
    return bool(settings.gmail_address and settings.gmail_app_password)


def _decode_header_value(value: str | None) -> str:
    """Subject/From headers can be MIME-encoded (RFC 2047, e.g. non-ASCII
    names/subjects) — decode_header handles both plain and encoded forms.
    """
    if not value:
        return ""
    parts = decode_header(value)
    return "".join(
        part.decode(encoding or "utf-8", errors="replace") if isinstance(part, bytes) else part
        for part, encoding in parts
    ).strip()


def _extract_body(msg: "email.message.Message") -> str:
    """Prefer the plain-text part; fall back to a crude HTML-tag strip if
    that's all the message has (most real mail clients send both). Pure
    function, no network — testable directly against a constructed
    email.message.Message.
    """
    if msg.is_multipart():
        for part in msg.walk():
            disposition = str(part.get("Content-Disposition") or "")
            if part.get_content_type() == "text/plain" and "attachment" not in disposition:
                charset = part.get_content_charset() or "utf-8"
                payload = part.get_payload(decode=True)
                return payload.decode(charset, errors="replace").strip() if payload else ""
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                charset = part.get_content_charset() or "utf-8"
                payload = part.get_payload(decode=True)
                html = payload.decode(charset, errors="replace") if payload else ""
                return _HTML_TAG_RE.sub("", html).strip()
        return ""

    charset = msg.get_content_charset() or "utf-8"
    payload = msg.get_payload(decode=True)
    return payload.decode(charset, errors="replace").strip() if payload else ""


def parse_message(raw_bytes: bytes) -> dict:
    """Parse one raw RFC 822 email into the shape inbound_service.py
    needs. Pure function (no network) — the unit-testable core of this
    module; see backend/tests/test_gmail_inbound.py.
    """
    msg = email.message_from_bytes(raw_bytes)
    _, sender_email = parseaddr(msg.get("From"))
    message_id = (msg.get("Message-Id") or "").strip() or None

    # Threading: the *root* of the References chain (the very first
    # message in the conversation) if present, else In-Reply-To (a direct
    # reply with no longer chain yet) — matches how mail clients thread.
    references = (msg.get("References") or "").strip()
    in_reply_to = (msg.get("In-Reply-To") or "").strip()
    thread_id = (references.split()[0] if references else in_reply_to) or None

    date_header = msg.get("Date")
    try:
        received_at = parsedate_to_datetime(date_header) if date_header else None
    except (TypeError, ValueError):
        received_at = None
    if received_at is None:
        received_at = datetime.now(timezone.utc)
    elif received_at.tzinfo is None:
        received_at = received_at.replace(tzinfo=timezone.utc)

    return {
        "sender_email": sender_email.strip().lower(),
        "subject": _decode_header_value(msg.get("Subject")),
        "body": _extract_body(msg),
        "message_id": message_id,
        "thread_id": thread_id,
        "received_at": received_at,
    }


def fetch_unread_messages() -> list[dict]:
    """Connect over IMAP, parse every UNSEEN message in INBOX, mark each
    \\Seen once parsed. Never raises: a connection/auth/parse failure is
    logged server-side and an empty list returned, so a scheduled poll or
    a manual "check now" click degrades to "no new messages" rather than
    crashing its caller — same fail-open contract every I/O boundary in
    this project already follows (communication adapters, rag_service).

    IMAP's \\Seen flag is one layer of "don't reprocess this" — set
    explicitly here rather than relied on as an implicit side effect of
    FETCH. inbound_service.py adds a second, independent layer
    (provider_message_id uniqueness), since a crash between fetch and
    flagging, or the mailbox being read from another client too, are both
    real possibilities \\Seen alone doesn't fully cover.
    """
    if not is_configured():
        return []

    messages: list[dict] = []
    try:
        with imaplib.IMAP4_SSL(_IMAP_HOST, _IMAP_PORT) as imap:
            imap.login(settings.gmail_address, settings.gmail_app_password)
            imap.select(_MAILBOX)

            status, data = imap.search(None, "UNSEEN")
            if status != "OK" or not data or not data[0]:
                return []

            for num in data[0].split():
                try:
                    status, msg_data = imap.fetch(num, "(RFC822)")
                    if status != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
                        continue
                    messages.append(parse_message(msg_data[0][1]))
                except Exception:
                    logger.exception("Failed to parse one inbound email (uid=%s)", num)
                finally:
                    imap.store(num, "+FLAGS", "\\Seen")
    except Exception:
        logger.exception("Gmail inbound IMAP fetch failed")
        return []

    return messages
