"""Public webhook routes — Step 3's inbound WhatsApp mechanism.

Unlike every other route in this project, these are hit directly by
Meta's servers, not by a logged-in admin — there is no session to check,
so `get_current_admin` doesn't apply here and can't be the security
boundary. Signature verification (communication.whatsapp_inbound) is:
every POST's body is HMAC-verified against the Meta App Secret *before*
anything in it is parsed, matched to a customer, or handed to the AI
Agent — an invalid or missing signature is rejected outright, not logged
and processed anyway. This is what makes a public, unauthenticated URL
safe to expose rather than "an insecure endpoint that accepts arbitrary
messages" (see whatsapp_inbound.py's own docstring).

Both endpoints degrade to "reject" when WHATSAPP_APP_SECRET /
WHATSAPP_WEBHOOK_VERIFY_TOKEN aren't configured (unset in every
environment as of Step 3 — see the Step 1/Step 3 reports on what's still
needed from Meta) — the same fail-closed contract every other
communication integration in this project already follows for its own
credentials, applied here to inbound trust rather than outbound send.
"""

import logging

from fastapi import APIRouter, Header, Query, Request, Response

from app.services import inbound_service
from app.services.communication import whatsapp_inbound

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.get("/whatsapp")
def verify_whatsapp_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    """Meta's one-time GET verification handshake, sent when the webhook
    URL is registered in the Meta App Dashboard. Query param names are
    fixed by Meta (hub.mode / hub.verify_token / hub.challenge) — Python
    identifiers can't contain dots, so each is explicitly aliased rather
    than relying on FastAPI's default (which would only match a literal
    `hub_mode` query param, not `hub.mode` — caught here by testing the
    route directly rather than assuming the naming would just work).
    """
    if whatsapp_inbound.verify_handshake(hub_mode, hub_verify_token):
        return Response(content=hub_challenge or "", media_type="text/plain")
    logger.warning("WhatsApp webhook verification failed (mode=%s)", hub_mode)
    return Response(status_code=403)


@router.post("/whatsapp")
async def receive_whatsapp_webhook(request: Request, x_hub_signature_256: str | None = Header(default=None)):
    """Real inbound messages. The raw body (not the parsed JSON) is what
    gets signature-verified — HMAC is computed over exact bytes, so
    verification has to happen before any parsing/re-serialization could
    change them.

    Always returns 200 to Meta once a request is accepted for processing
    (even if a downstream step like AI drafting later fails — see
    inbound_service.py's own fail-safe handling) — a non-2xx response
    makes Meta retry the same webhook delivery, so anything already
    recorded should not be re-signaled as failed. An invalid signature is
    the one case this rejects outright, since accepting and silently
    discarding an unverified request would defeat the point of verifying
    at all.
    """
    raw_body = await request.body()
    if not whatsapp_inbound.verify_signature(raw_body, x_hub_signature_256):
        logger.warning("WhatsApp webhook signature verification failed")
        return Response(status_code=403)

    try:
        payload = await request.json()
    except Exception:
        logger.exception("WhatsApp webhook payload was not valid JSON")
        return Response(status_code=200)  # accepted, nothing usable to process

    for parsed in whatsapp_inbound.parse_webhook_payload(payload):
        try:
            inbound_service.process_inbound_whatsapp(parsed)
        except Exception:
            logger.exception("Failed to process one inbound WhatsApp message")

    return Response(status_code=200)
