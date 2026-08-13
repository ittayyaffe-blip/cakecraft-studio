"""Public Twilio webhook route — the Twilio WhatsApp Sandbox's inbound
mechanism, parallel to webhooks.py's Meta route and deliberately kept in
its own file/router rather than added to that one: genuinely different
protocol (form-encoded body, HMAC-SHA1-over-URL+params signature, no
GET-handshake concept at all), and keeping it separate means this file's
diff is the *entire* Twilio surface here, with zero lines of the existing
Meta route touched.

Same security posture as webhooks.py: hit directly by Twilio's servers,
not a logged-in admin, so `get_current_admin` doesn't apply and can't be
the boundary. Every POST's exact request URL + form params are
signature-verified (communication.twilio_whatsapp_inbound) *before*
anything is parsed further, matched to a customer, or handed to the AI
Agent — an invalid or missing signature is rejected outright. Fails
closed when TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN aren't configured, same
contract as every other credential-gated integration in this project.
"""

import logging

from fastapi import APIRouter, Request, Response

from app.services import inbound_service
from app.services.communication import twilio_whatsapp_inbound

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/twilio-whatsapp")
async def receive_twilio_whatsapp_webhook(request: Request):
    """Real inbound Sandbox messages. Twilio signs the *parsed* form
    params (not raw bytes the way Meta does), so this reads
    `request.form()` rather than `request.body()` — verification still
    has to happen before anything in those params is trusted.

    Always returns a bare 200 (empty TwiML) once a request is accepted for
    processing, even if a downstream step (AI drafting) later fails — see
    inbound_service.py's own fail-safe handling — except an invalid
    signature, which is rejected outright with 403. No inline auto-reply
    is ever generated here: this project's human-in-the-loop principle
    holds exactly as it does for every other channel — a draft is created,
    a human approves it, only then does anything send.
    """
    form = await request.form()
    params = dict(form)
    signature = request.headers.get("X-Twilio-Signature")

    # See twilio_whatsapp_inbound.external_url's own docstring: request.url
    # reports Railway's internal http:// URL, not the https:// URL Twilio
    # actually signed, so this reconstructs the real one from the
    # platform-set forwarded headers before verifying.
    url = twilio_whatsapp_inbound.external_url(
        str(request.url),
        request.headers.get("X-Forwarded-Proto"),
        request.headers.get("X-Forwarded-Host"),
    )

    if not twilio_whatsapp_inbound.verify_signature(url, params, signature):
        logger.warning("Twilio WhatsApp webhook signature verification failed")
        return Response(status_code=403)

    parsed = twilio_whatsapp_inbound.parse_webhook_payload(params)
    if parsed is not None:
        try:
            inbound_service.process_inbound_whatsapp(parsed)
        except Exception:
            logger.exception("Failed to process inbound Twilio WhatsApp message")

    return Response(status_code=200, media_type="text/xml", content="<Response></Response>")
