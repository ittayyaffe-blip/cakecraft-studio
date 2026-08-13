"""Standalone Twilio WhatsApp diagnostic — NOT part of the production app,
does not import or touch app/services/communication/twilio_whatsapp_adapter.py
or any other CakeCraft code. The one job here: find out, from Twilio's own
API responses, whether this Twilio account can actually send a WhatsApp
Sandbox message right now — before touching the real adapter/integration.

Credentials come ONLY from environment variables, never hardcoded, never
printed:

    TWILIO_ACCOUNT_SID       (required)
    TWILIO_AUTH_TOKEN        (required — never logged, never echoed)
    TWILIO_WHATSAPP_FROM     (optional, defaults to the public Sandbox
                              number whatsapp:+14155238886)
    TWILIO_WHATSAPP_TEST_TO  (optional — E.164 WhatsApp format,
                              e.g. whatsapp:+15551234567; if unset, this
                              script only verifies authentication/account
                              access and skips the send attempt)

Uses the official `twilio` Python SDK (already a pinned project
dependency in backend/requirements.txt — added earlier for inbound
signature verification, see
backend/app/services/communication/twilio_whatsapp_inbound.py) purely
for its structured TwilioRestException (.status/.code/.msg) — this
script does not send raw HTTP itself, and does not import anything from
`backend/app/`, matching this repo's existing tools/ convention (see
tools/evaluate_forecast_models.py) of standalone scripts run with the
project's venv but never deployed with the app.

Run with the backend venv active (from anywhere in the repo):

    python tools/test_twilio_whatsapp.py

Real credentials should come from the environment the process is run in
(e.g. `railway run --service web python tools/test_twilio_whatsapp.py`),
never pasted into a file or the command line.
"""

import os
import sys
from pathlib import Path

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

_DEFAULT_FROM = "whatsapp:+14155238886"
_TEST_BODY = "CakeCraft Studio Twilio diagnostic — please ignore."


def _redact(value: str | None) -> str:
    """For diagnostic *output* only — never used to decide anything, just
    so a human reading this script's output can confirm which account
    it's checking without the token ever being visible. Shows only that
    a value is present and its length, nothing recoverable from it.
    """
    if not value:
        return "(not set)"
    return f"(set, {len(value)} chars)"


def check_auth(client: Client, account_sid: str) -> bool:
    print("=== Step 1: authentication / account access ===")
    try:
        account = client.api.accounts(account_sid).fetch()
    except TwilioRestException as exc:
        print("FAILED to authenticate / fetch account.")
        print(f"  HTTP status : {exc.status}")
        print(f"  Twilio code : {exc.code}")
        print(f"  Twilio msg  : {exc.msg}")
        return False
    except Exception as exc:
        print(f"FAILED (non-Twilio error): {exc!r}")
        return False

    print("OK — authenticated.")
    print(f"  Account SID    : {account.sid}")
    print(f"  Friendly name  : {account.friendly_name}")
    print(f"  Status         : {account.status}")
    print(f"  Type           : {account.type}")
    return True


def attempt_whatsapp_send(client: Client, from_number: str, to_number: str) -> None:
    print("\n=== Step 2: attempt ONE WhatsApp message send ===")
    print(f"  From: {from_number}")
    print(f"  To  : {to_number}")
    try:
        message = client.messages.create(from_=from_number, to=to_number, body=_TEST_BODY)
    except TwilioRestException as exc:
        print("\nRESULT: FAILED (Twilio rejected the request)")
        print(f"  HTTP status : {exc.status}")
        print(f"  Twilio code : {exc.code}")
        print(f"  Twilio msg  : {exc.msg}")
        print(f"  More info   : {getattr(exc, 'details', None) or exc.uri}")
        return
    except Exception as exc:
        print(f"\nRESULT: FAILED (non-Twilio error): {exc!r}")
        return

    print("\nRESULT: Twilio accepted the request.")
    print(f"  Message SID : {message.sid}")
    print(f"  Status      : {message.status}")
    print(f"  Error code  : {message.error_code}")
    print(f"  Error msg   : {message.error_message}")
    if message.error_code:
        print(
            "\n  NOTE: Twilio accepted the API call but the message itself carries an "
            "error (e.g. undelivered) — check Status/Error code above before calling this a GO."
        )


def attempt_via_cakecraft_adapter(test_to: str) -> None:
    """Stage D: send through the ACTUAL CakeCraft communication layer
    (backend/app/services/communication/twilio_whatsapp_adapter.py's real
    send()) instead of calling the Twilio SDK directly the way Stage C
    does — proves the adapter code path itself, not just that Twilio's
    API is reachable. Still standalone: imports the real adapter module
    (read-only, not modified) rather than duplicating its logic, but
    never touches notification_service/the queue/approval workflow — a
    bare notification-shaped dict, not a real DB row.

    `test_to` is read from the environment by the caller (main()), same
    as Stage C — never hard-coded here, matching the same rule the real
    adapter/production code already follows for its Sandbox FROM number
    (a public constant) vs. any real recipient (never hard-coded).
    """
    backend_path = Path(__file__).resolve().parent.parent / "backend"
    sys.path.insert(0, str(backend_path))
    from app.services.communication import twilio_whatsapp_adapter  # noqa: E402

    print("\n=== Stage D: send via the real CakeCraft twilio_whatsapp_adapter.send() ===")
    print(f"  Adapter module : {twilio_whatsapp_adapter.__file__}")
    print(f"  channel        : {twilio_whatsapp_adapter.channel}")
    print(f"  is_configured  : {twilio_whatsapp_adapter.is_configured()}")

    notification = {
        "id": "diagnostic-stage-d",
        "subject": None,
        "body": "🎂 CakeCraft Studio test message — WhatsApp integration is working successfully.",
        "customers": {"phone": test_to},
    }
    result = twilio_whatsapp_adapter.send(notification)

    print(f"\nRESULT: success={result.success}")
    print(f"  provider_message_id : {result.provider_message_id}")
    print(f"  error                : {result.error}")


def main() -> int:
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_WHATSAPP_FROM", _DEFAULT_FROM)
    test_to = os.environ.get("TWILIO_WHATSAPP_TEST_TO")
    via_adapter = "--via-adapter" in sys.argv

    print("CakeCraft Studio — Twilio WhatsApp diagnostic")
    print("=" * 50)
    print(f"TWILIO_ACCOUNT_SID      : {account_sid or '(not set)'}")
    print(f"TWILIO_AUTH_TOKEN       : {_redact(auth_token)}")
    print(f"TWILIO_WHATSAPP_FROM    : {from_number}")
    print(f"TWILIO_WHATSAPP_TEST_TO : {test_to or '(not set — send step will be skipped)'}")
    print()

    if not account_sid or not auth_token:
        print("FAILED: TWILIO_ACCOUNT_SID and/or TWILIO_AUTH_TOKEN not set in the environment.")
        return 1

    client = Client(account_sid, auth_token)

    if not check_auth(client, account_sid):
        return 1

    if not test_to:
        print("\nTWILIO_WHATSAPP_TEST_TO not set — stopping after the auth check.")
        print("Set it (whatsapp:+<countrycode><number>) and re-run to attempt a real send.")
        return 0

    if via_adapter:
        attempt_via_cakecraft_adapter(test_to)
    else:
        attempt_whatsapp_send(client, from_number, test_to)
    return 0


if __name__ == "__main__":
    sys.exit(main())
