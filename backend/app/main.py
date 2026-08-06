from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import collections, designer, health, orders, templates
from app.api.routes.admin import agent as admin_agent
from app.api.routes.admin import auth as admin_auth
from app.api.routes.admin import briefing as admin_briefing
from app.api.routes.admin import customers as admin_customers
from app.api.routes.admin import dashboard as admin_dashboard
from app.api.routes.admin import notifications as admin_notifications
from app.api.routes.admin import orders as admin_orders
from app.api.routes.admin import rag as admin_rag
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
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
app.include_router(admin_auth.router)
app.include_router(admin_dashboard.router)
app.include_router(admin_briefing.router)
app.include_router(admin_orders.router)
app.include_router(admin_customers.router)
app.include_router(admin_notifications.router)
app.include_router(admin_rag.router)
app.include_router(admin_agent.router)


@app.get("/")
def root():
    return {
        "message": "Welcome to CakeCraft Studio!"
    }
    