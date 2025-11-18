from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import db  # moteur/metadata centralisés
from app.config import AppInfo, SCHEDULER_ENABLED, get_settings
from app.core.logging import get_logger, setup_logging
import app.models  # enregistre les tables
from app.routers import apikeys, get_api_router
from app.services.cron import expire_mandates_once
from app.utils.errors import error_response

settings = get_settings()
logger = get_logger(__name__)
scheduler: AsyncIOScheduler | None = None
ALLOWED_CREATE_ENV = {"dev", "local", "test"}

# -------- Lifespan (nouveau mécanisme) --------
@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("Application startup", extra={"env": settings.app_env})
    if settings.psp_webhook_secret is None:
        raise RuntimeError("PSP_WEBHOOK_SECRET manquant : configurez la variable d'environnement ou le fichier .env")
    db.init_engine()  # sync, idempotent
    env_lower = settings.app_env.lower()
    if settings.ALLOW_DB_CREATE_ALL and env_lower in ALLOWED_CREATE_ENV:
        logger.warning(
            "Running Base.metadata.create_all() because APP_ENV=%s and ALLOW_DB_CREATE_ALL=True",
            settings.app_env,
        )
        db.create_all()
    else:
        logger.info(
            "Skipping create_all(); use Alembic migrations. APP_ENV=%s, ALLOW_DB_CREATE_ALL=%s",
            settings.app_env,
            settings.ALLOW_DB_CREATE_ALL,
        )
    # NOTE: In multi-replica deployments, enable SCHEDULER_ENABLED=true on ONE runner only (others=false).
    # For 1.0.0 consider external cron/worker or APScheduler with a distributed job store/lock.
    # Lancer le scheduler uniquement sur l'instance désignée (cf. déploiement multi-runner).
    if SCHEDULER_ENABLED:
        global scheduler
        scheduler = AsyncIOScheduler()
        scheduler.start()
        scheduler.add_job(
            expire_mandates_once,
            "interval",
            minutes=60,
            id="expire-mandates",
            replace_existing=True,
        )
        if settings.app_env.lower() != "dev":
            logger.warning(
                "APScheduler enabled with in-memory store; ensure only one runner has SCHEDULER_ENABLED=1 in production.",
                extra={"env": settings.app_env},
            )
    try:
        yield
    finally:
        if scheduler:
            scheduler.shutdown(wait=False)
        db.close_engine()
        logger.info("Application shutdown", extra={"env": settings.app_env})

app_info = AppInfo()

app = FastAPI(title=app_info.name, version=app_info.version, lifespan=lifespan)

# Middleware & routes
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)

if settings.PROMETHEUS_ENABLED:
    from starlette_exporter import PrometheusMiddleware, handle_metrics

    app.add_middleware(PrometheusMiddleware)
    app.add_route("/metrics", handle_metrics)

if settings.SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(dsn=settings.SENTRY_DSN, traces_sample_rate=0.2)
app.include_router(get_api_router())
app.include_router(apikeys.router)

# Handlers d’erreurs
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception", exc_info=exc)
    payload = error_response("INTERNAL_SERVER_ERROR", "An unexpected error occurred.")
    return JSONResponse(status_code=500, content=payload)

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and "error" in detail:
        content: dict[str, Any] = detail
    else:
        content = error_response("HTTP_ERROR", str(detail))
    return JSONResponse(status_code=exc.status_code, content=content, headers=getattr(exc, "headers", None))

__all__ = ["app"]
