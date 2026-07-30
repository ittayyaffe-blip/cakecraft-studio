from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


from app.api.routes import collections, health, orders, templates
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
