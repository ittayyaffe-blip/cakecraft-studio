import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chat, collections, designer, health, orders, templates, webhooks
from app.api.routes.admin import agent as admin_agent
from app.api.routes.admin import auth as admin_auth
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

# Allow all origins (demo/project deployment)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
app.include_router(webhooks.router)


@app.get("/")
def root():
    return {
        "message": "Welcome to CakeCraft Studio!"
    }
    