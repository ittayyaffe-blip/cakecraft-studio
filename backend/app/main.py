from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import collections, designer, health, orders, templates
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


@app.get("/")
def root():
    return {
        "message": "Welcome to CakeCraft Studio!"
    }
    