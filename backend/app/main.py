from fastapi import FastAPI

from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine
from app.models import User  # noqa: F401

app = FastAPI(title=settings.app_name)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


app.include_router(health_router, prefix=settings.api_prefix, tags=["system"])
app.include_router(auth_router, prefix=settings.api_prefix)
