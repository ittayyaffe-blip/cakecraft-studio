from fastapi import FastAPI

from app.api.routes import collections, health, orders, templates
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
)

app.include_router(health.router)
app.include_router(templates.router)
app.include_router(collections.router)
app.include_router(orders.router)


@app.get("/")
def root():
    return {
        "message": "Welcome to CakeCraft Studio!"
    }
