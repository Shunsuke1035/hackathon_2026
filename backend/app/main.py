from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.analysis import router as analysis_router
from app.api.routes.auth import router as auth_router
from app.api.routes.facility import router as facility_router
from app.api.routes.health import router as health_router
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine
from app.models import Facility, User  # noqa: F401

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


app.include_router(health_router, prefix=settings.api_prefix, tags=["system"])
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(facility_router, prefix=settings.api_prefix)
app.include_router(analysis_router, prefix=settings.api_prefix)
