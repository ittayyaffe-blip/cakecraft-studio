import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chat, collections, designer, health, orders, templates, webhooks, webhooks_twilio
from app.api.routes.admin import agent as admin_agent
from app.api.routes.admin import auth as admin_auth
from app.api.routes.admin import bakery_manager as admin_bakery_manager
from app.api.routes.admin import briefing as admin_briefing
from app.api.routes.admin import catalog as admin_catalog
from app.api.routes.admin import communications as admin_communications
from app.api.routes.admin import customers as admin_customers
from app.api.routes.admin import dashboard as admin_dashboard
from app.api.routes.admin import notifications as admin_notifications
from app.api.routes.admin import orders as admin_orders
from app.api.routes.admin import rag as admin_rag
from app.core.config import settings
from app.services import inbound_service
from app.services.communication import gmail_inbound

logger = logging.getLogger(__name__)

# Step 3 — inbound email: the smallest reliable mechanism for this
# project's scale (see communication/gmail_inbound.py's own docstring for
# why IMAP polling over Gmail push/Pub-Sub). Runs inside this same process
# rather than a separate worker/cron — Railway runs this service as a
# single always-on replica, so a plain asyncio background task needs no
# new infrastructure and no new dependency (asyncio is stdlib). Checks
# immediately on startup, then every interval — a restart shouldn't mean
# waiting a full interval before the first check.
_EMAIL_POLL_INTERVAL_SECONDS = 120


async def _email_poll_loop() -> None:
    while True:
        if gmail_inbound.is_configured():
            try:
                inbound_service.check_for_new_email()
            except Exception:
                logger.exception("Background inbound-email poll failed")
        await asyncio.sleep(_EMAIL_POLL_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    poll_task = asyncio.create_task(_email_poll_loop())
    yield
    poll_task.cancel()


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    lifespan=lifespan,
)

# Allow all origins (demo/project deployment). Considered restricting this
# to the deployed frontend origin during the Final Security Hardening Pass
# — deferred rather than risking breaking a legitimate access pattern this
# app doesn't fully control from here (local dev on an unpredictable port,
# the LAN-IP scenario api.js's own comment describes, direct file:// opens
# during grading). Safe as-is because allow_credentials=False — nothing
# here relies on cookies, so wildcard origins cannot be leveraged for a
# credentialed cross-origin request; every admin action still requires a
# valid bearer token regardless of the calling origin. See
# docs/FINAL_ARCHITECTURE.md's Security Boundaries section.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Security response headers — Final Security Hardening Pass. This service
# only ever returns JSON (or, for the Twilio webhook, a bare TwiML XML
# body) — never an HTML document — so a maximally restrictive CSP here is
# pure defense-in-depth with zero functional risk: nothing in a JSON/XML
# API response is a browsing context CSP would ever need to relax for.
# The CSP that actually matters for the customer/admin-facing HTML pages
# lives with the frontend's own static file server (frontend/serve.json)
# — a JSON API response body cannot execute a script or load a stylesheet
# regardless of what header is attached to it, so duplicating that page-
# level policy here would add nothing real.
#
# Strict-Transport-Security is safe to add unconditionally: verified live
# that Railway's edge already 301-redirects every plain-HTTP request to
# HTTPS for this domain, so this header only tells browsers to skip that
# now-redundant first HTTP round trip next time, never introduces a new
# way to be locked out. `includeSubDomains` only reaches subdomains of
# this one service's own Railway hostname (e.g. `foo.web-production-....
# up.railway.app`, which doesn't exist), not sibling Railway apps.
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    for key, value in _SECURITY_HEADERS.items():
        response.headers[key] = value
    return response


app.include_router(health.router)
app.include_router(templates.router)
app.include_router(collections.router)
app.include_router(designer.router)
app.include_router(orders.router)
app.include_router(chat.router)
app.include_router(admin_auth.router)
app.include_router(admin_dashboard.router)
app.include_router(admin_briefing.router)
app.include_router(admin_orders.router)
app.include_router(admin_customers.router)
app.include_router(admin_notifications.router)
app.include_router(admin_rag.router)
app.include_router(admin_agent.router)
app.include_router(admin_communications.router)
app.include_router(admin_catalog.router)
app.include_router(admin_bakery_manager.router)
app.include_router(webhooks.router)
app.include_router(webhooks_twilio.router)


@app.get("/")
def root():
    return {
        "message": "Welcome to CakeCraft Studio!"
    }
    