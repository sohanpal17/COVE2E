"""COVE2E backend — FastAPI application factory."""
import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers import (
    actions,
    auth,
    chat,
    claims,
    dashboard,
    demo,
    discovery,
    escalations,
    incidents,
    journeys,
    mock_insurer,
    notifications,
    policies,
    voice,
)
from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cove2e")

settings = get_settings()

app = FastAPI(
    title="COVE2E — Coverage End-to-End",
    description=(
        "AI-powered insurance journey teammate. The LLM (Sarvam) proposes; FastAPI decides through the "
        "deterministic Investigation/Recovery engines and the Action Gate; n8n executes; the Outcome Verifier confirms."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth, dashboard, policies, incidents, claims, actions, journeys, voice, escalations, notifications, discovery, demo, mock_insurer, chat):
    app.include_router(r.router)


@app.on_event("startup")
def on_startup() -> None:
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    # Alembic owns the schema in production; for local/demo convenience we also create missing tables.
    if not settings.is_production:
        Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        from app.services.demo_service import ensure_demo_user, ensure_products

        ensure_products(db)
        ensure_demo_user(db, "demo")
        db.commit()
    logger.info("COVE2E started. DB=%s demo_mode=%s sarvam=%s cognee=%s", settings.DATABASE_URL.split("@")[-1], settings.DEMO_MODE, settings.sarvam_configured, settings.COGNEE_ENABLED)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal error. The action was not completed.", "error": exc.__class__.__name__})


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "service": "cove2e-backend", "demo_mode": settings.DEMO_MODE}
