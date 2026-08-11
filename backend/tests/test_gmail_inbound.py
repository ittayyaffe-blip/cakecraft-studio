"""Dependency-free self-check for gmail_inbound.py's pure parsing logic —
no network/IMAP connection required. Run from `backend/`:

    python -m tests.test_gmail_inbound

fetch_unread_messages() itself (the real IMAP connection) is exercised
live instead — see the Step 3 report's "Live verification" section.
Everything here is parse_message()/is_configured(), tested directly
against real constructed email.message objects.
"""

from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from unittest.mock import patch

from app.core.config import settings
from app.services.communication import gmail_inbound


def _build_raw_email(**overrides) -> bytes:
    msg = EmailMessage()
    msg["From"] = overrides.get("from_", "Jane Doe <jane@example.com>")
    msg["To"] = "hello@maisondegateau.test"
    msg["Subject"] = overrides.get("subject", "Question about my order")
    msg["Message-Id"] = overrides.get("message_id", "<abc123@mail.example.com>")
    if "in_reply_to" in overrides:
        msg["In-Reply-To"] = overrides["in_reply_to"]
    if "references" in overrides:
        msg["References"] = overrides["references"]
    msg.set_content(overrides.get("body", "Hi, can I change my cake size?"))
    return msg.as_bytes()


def test_parse_message_extracts_sender_subject_body_and_message_id():
    parsed = gmail_inbound.parse_message(_build_raw_email())
    assert parsed["sender_email"] == "jane@example.com"
    assert parsed["subject"] == "Question about my order"
    assert "change my cake size" in parsed["body"]
    assert parsed["message_id"] == "<abc123@mail.example.com>"


def test_parse_message_lowercases_and_strips_sender_email():
    parsed = gmail_inbound.parse_message(_build_raw_email(from_="Jane Doe <JANE@EXAMPLE.COM>"))
    assert parsed["sender_email"] == "jane@example.com"


def test_parse_message_thread_id_prefers_references_root_over_in_reply_to():
    parsed = gmail_inbound.parse_message(
        _build_raw_email(references="<root@x> <second@x>", in_reply_to="<second@x>")
    )
    assert parsed["thread_id"] == "<root@x>"


def test_parse_message_thread_id_falls_back_to_in_reply_to():
    parsed = gmail_inbound.parse_message(_build_raw_email(in_reply_to="<direct-reply@x>"))
    assert parsed["thread_id"] == "<direct-reply@x>"


def test_parse_message_thread_id_none_for_a_fresh_conversation():
    parsed = gmail_inbound.parse_message(_build_raw_email())
    assert parsed["thread_id"] is None


def test_parse_message_extracts_plain_text_part_from_multipart():
    msg = MIMEMultipart("alternative")
    msg["From"] = "jane@example.com"
    msg["Subject"] = "Multipart"
    msg["Message-Id"] = "<multipart@x>"
    msg.attach(MIMEText("Plain text version", "plain"))
    msg.attach(MIMEText("<p>HTML version</p>", "html"))
    parsed = gmail_inbound.parse_message(msg.as_bytes())
    assert parsed["body"] == "Plain text version"


def test_parse_message_strips_html_tags_when_only_html_part_exists():
    msg = MIMEMultipart("alternative")
    msg["From"] = "jane@example.com"
    msg["Subject"] = "HTML only"
    msg["Message-Id"] = "<html-only@x>"
    msg.attach(MIMEText("<p>Hello <b>there</b></p>", "html"))
    parsed = gmail_inbound.parse_message(msg.as_bytes())
    assert "Hello" in parsed["body"]
    assert "<" not in parsed["body"]


def test_parse_message_missing_message_id_returns_none_not_a_crash():
    msg = EmailMessage()
    msg["From"] = "jane@example.com"
    msg["Subject"] = "No Message-Id"
    msg.set_content("Hi")
    parsed = gmail_inbound.parse_message(msg.as_bytes())
    assert parsed["message_id"] is None


def test_is_configured_false_when_credentials_unset():
    with patch.object(settings, "gmail_address", None), patch.object(settings, "gmail_app_password", None):
        assert gmail_inbound.is_configured() is False


def test_is_configured_true_when_both_credentials_set():
    with patch.object(settings, "gmail_address", "hello@example.com"), patch.object(
        settings, "gmail_app_password", "app-password"
    ):
        assert gmail_inbound.is_configured() is True


def test_fetch_unread_messages_returns_empty_list_when_not_configured():
    with patch.object(settings, "gmail_address", None):
        assert gmail_inbound.fetch_unread_messages() == []


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
