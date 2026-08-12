import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")


class Settings:
    app_name: str = "CakeCraft Studio API"
    version: str = "0.1.0"

    supabase_url: str = os.environ["SUPABASE_URL"]
    supabase_key: str = os.environ["SUPABASE_KEY"]

    # --- Auth & security ----------------------------------------------
    # Admin/staff authentication (app/services/auth_service.py) reuses this
    # same Supabase project — no separate identity provider and no extra
    # required env vars. This block is the one place any future auth or
    # security-related setting belongs, so it stays centralized instead of
    # scattered across services as the admin surface grows.
    #
    # Session scope revoked on admin logout: "global" (every session/device
    # for that user), "local" (only the session being logged out), or
    # "others" (every session except this one). See
    # app/services/auth_service.py:logout.
    admin_signout_scope: str = os.environ.get("ADMIN_SIGNOUT_SCOPE", "global")

    # --- Communication adapters (Sprint 3) -----------------------------
    # Optional: both unset (the default today) means the Gmail adapter
    # reports itself as not configured
    # (app/services/communication/gmail_adapter.py:is_configured) and
    # notification_service.send() falls back to its original stub
    # behavior — nothing actually delivered, but nothing broken either.
    # The whole notification engine works identically with or without
    # these set, the same feature-flag-by-presence pattern
    # admin_signout_scope above already established.
    #
    # gmail_address: the sending Gmail account.
    # gmail_app_password: a Gmail *app password* (Google Account settings
    # > Security > App passwords), not the account's real login password —
    # never commit a real one; set it on Railway as a service env var.
    gmail_address: str | None = os.environ.get("GMAIL_ADDRESS")
    gmail_app_password: str | None = os.environ.get("GMAIL_APP_PASSWORD")

    # Resend (https://resend.com) — replaces raw SMTP as of this fix: Railway
    # blocks outbound SMTP ports entirely at the network level (confirmed by
    # direct in-container testing: ports 25/465/587/2525 to smtp.gmail.com
    # all silently time out, while HTTPS egress works instantly), so no
    # amount of SMTP-side code can ever deliver mail from this host — see
    # gmail_adapter.py. Resend's HTTP API sends over the same HTTPS port
    # every other outbound call in this project already uses. Same
    # feature-flag-by-presence contract as every setting above: unset means
    # gmail_adapter.is_configured() is False and the app degrades exactly as
    # it always has with no email credentials configured.
    resend_api_key: str | None = os.environ.get("RESEND_API_KEY")

    # WhatsApp Business Cloud API (Meta) — Sprint 4. Same contract as the
    # Gmail settings above: both unset (the default today) means
    # app/services/communication/whatsapp_adapter.py reports itself as
    # not configured and notification_service.send() falls back to its
    # stub behavior. Nothing else in this project changes because these
    # are set or not.
    #
    # whatsapp_access_token: a Meta system-user or temporary access token
    # for the WhatsApp Business app.
    # whatsapp_phone_number_id: the Cloud API phone number ID (not the
    # phone number itself) the business sends from.
    whatsapp_access_token: str | None = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    whatsapp_phone_number_id: str | None = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")

    # Inbound WhatsApp (Step 3) — the Meta Cloud API webhook needs two
    # additional secrets the outbound adapter above never needed:
    # whatsapp_webhook_verify_token: an arbitrary string *we* choose, given
    # to Meta when configuring the webhook URL; Meta echoes it back on the
    # one-time GET verification handshake (app/api/routes/webhooks.py) —
    # this is what proves the person configuring the webhook is us, not a
    # stranger, not a delivery-content secret.
    # whatsapp_app_secret: the Meta App Secret, used to verify the
    # X-Hub-Signature-256 header Meta signs every real webhook POST with
    # (HMAC-SHA256 over the raw body) — this is what proves an inbound
    # request actually came from Meta, not an arbitrary POST to a public
    # URL. Both unset today means the webhook route rejects every request
    # rather than accepting unverified ones — see whatsapp_inbound.py.
    whatsapp_webhook_verify_token: str | None = os.environ.get("WHATSAPP_WEBHOOK_VERIFY_TOKEN")
    whatsapp_app_secret: str | None = os.environ.get("WHATSAPP_APP_SECRET")

    # Inbound Gmail (Step 3) — IMAP polling of the *same* Gmail account
    # GMAIL_ADDRESS/GMAIL_APP_PASSWORD above already sends from (an App
    # Password authorizes IMAP too, not just SMTP — no new Google-side
    # setup, no new credential). Unset (i.e. Gmail not configured at all)
    # means inbound polling is skipped the same way outbound send already
    # degrades — see communication/gmail_inbound.py.

    # --- Business Intelligence Layer (RAG + AI Operations Agent) -------
    # Optional, same feature-flag-by-presence pattern as the communication
    # adapters above: unset means rag_service.py/agent_service.py report
    # themselves as not configured and degrade to a clear message rather
    # than a crash — never a required dependency for the rest of the app.
    anthropic_api_key: str | None = os.environ.get("ANTHROPIC_API_KEY")


settings = Settings()
