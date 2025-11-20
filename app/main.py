from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import db  # moteur/metadata centralisés
from app.config import AppInfo, get_settings
from app.core.logging import get_logger, setup_logging
from app.core.runtime_state import set_scheduler_active
import app.models  # enregistre les tables
from app.routers import apikeys, get_api_router, kct_public
from app.services.cron import expire_mandates_once
from app.services.scheduler_lock import (
    refresh_scheduler_lock,
    release_scheduler_lock,
    try_acquire_scheduler_lock,
)
from app.utils.errors import error_response

logger = get_logger(__name__)
scheduler: AsyncIOScheduler | None = None
ALLOWED_CREATE_ENV = {"dev", "local", "test"}


def _current_settings():
    """Return fresh settings (TTL-cached within get_settings)."""

    return get_settings()


def _configure_middlewares(fastapi_app: FastAPI) -> None:
    """Configure middleware using a fresh snapshot of the settings."""

    runtime_settings = _current_settings()
    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime_settings.CORS_ALLOW_ORIGINS,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    )

    if runtime_settings.PROMETHEUS_ENABLED:
        from starlette_exporter import PrometheusMiddleware, handle_metrics

        fastapi_app.add_middleware(PrometheusMiddleware)
        fastapi_app.add_route("/metrics", handle_metrics)

    if runtime_settings.SENTRY_DSN:
        import sentry_sdk

        sentry_sdk.init(dsn=runtime_settings.SENTRY_DSN, traces_sample_rate=0.2)


def _assert_psp_webhook_secrets(settings: Any) -> None:
    """Fail-fast when PSP webhook secrets are missing in non-dev environments."""

    secrets_configured = bool(settings.psp_webhook_secret or settings.psp_webhook_secret_next)
    env_lower = settings.app_env.lower()
    if env_lower != "dev" and not secrets_configured:
        logger.error(
            "PSP webhook secrets are missing; configure PSP_WEBHOOK_SECRET or PSP_WEBHOOK_SECRET_NEXT before startup.",
            extra={"env": settings.app_env},
        )
        raise RuntimeError("Missing PSP webhook secrets in non-dev environment.")
    if env_lower == "dev" and not secrets_configured:
        logger.warning(
            "PSP webhook secrets are not configured; allowed in dev only.",
            extra={"env": settings.app_env},
        )


# -------- Lifespan (nouveau mécanisme) --------
@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings = _current_settings()
    logger.info("Application startup", extra={"env": settings.app_env})
    _assert_psp_webhook_secrets(settings)

    if settings.psp_webhook_secret is None and settings.psp_webhook_secret_next:
        logger.warning(
            "Primary PSP webhook secret unset; relying on PSP_WEBHOOK_SECRET_NEXT only.",
            extra={"env": settings.app_env},
        )
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
    set_scheduler_active(False)
    lock_acquired = False
    if settings.SCHEDULER_ENABLED:
        lock_acquired = try_acquire_scheduler_lock()
        if lock_acquired:
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
            scheduler.add_job(
                refresh_scheduler_lock,
                "interval",
                seconds=60,
                id="scheduler-lock-heartbeat",
                replace_existing=True,
            )
            set_scheduler_active(True)
            if settings.app_env.lower() != "dev":
                logger.warning(
                    "APScheduler enabled with DB lock; ensure only one runner has SCHEDULER_ENABLED=1 in production.",
                    extra={"env": settings.app_env},
                )
        else:
            logger.warning(
                "Scheduler disabled because lock is already held by another instance.",
                extra={"env": settings.app_env},
            )
    try:
        yield
    finally:
        if scheduler:
            scheduler.shutdown(wait=False)
        if lock_acquired:
            release_scheduler_lock()
        set_scheduler_active(False)
        db.close_engine()
        logger.info("Application shutdown", extra={"env": settings.app_env})

app_info = AppInfo()

app = FastAPI(title=app_info.name, version=app_info.version, lifespan=lifespan)

# Middleware & routes
_configure_middlewares(app)
app.include_router(get_api_router())
app.include_router(apikeys.router)
app.include_router(kct_public.router)

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
