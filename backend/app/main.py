import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


from app.api.routes import collections, designer, health, orders, templates
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
)

# Dev-friendly by default: localhost, 127.0.0.1, and any 192.168.x.x LAN
# address, on any port. Set CORS_ALLOW_ORIGIN_REGEX on Railway to also
# allow the deployed production frontend's origin, without a code change.
DEFAULT_CORS_ORIGIN_REGEX = r"^http://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3})(:\d+)?$"

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=os.environ.get("CORS_ALLOW_ORIGIN_REGEX", DEFAULT_CORS_ORIGIN_REGEX),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(health.router)
app.include_router(templates.router)
app.include_router(collections.router)
app.include_router(designer.router)
app.include_router(orders.router)


@app.get("/")
def root():
    return {
        "message": "Welcome to CakeCraft Studio!"
    }
