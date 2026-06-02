"""FastAPI application factory and health-check endpoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint
)
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.db.session import engine

logger = structlog.get_logger("app")


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    """
    Startup:
        - Setup logging
        - Run migrations

    Shutdown:
        - Dispose DB engine
    """

    setup_logging(settings.LOG_LEVEL)

    logger.info(
        "app_startup",
        env=settings.APP_ENV
    )

    # -------------------------------------------------------------------
    # RUN DATABASE MIGRATIONS
    # -------------------------------------------------------------------

    import subprocess
    import sys

    try:

        subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "head"
            ],
            check=True
        )

        logger.info(
            "✅ Database migrations completed"
        )

    except Exception:

        logger.exception(
            "❌ migrations_failed"
        )

    # -------------------------------------------------------------------
    # RUN SEED (idempotent — safe on every startup)
    # -------------------------------------------------------------------

    try:

        from scripts.seed import seed
        await seed()
        logger.info("✅ Database seed completed")

    except Exception:

        logger.exception("❌ seed_failed")

    # -------------------------------------------------------------------
    # APP RUNNING
    # -------------------------------------------------------------------

    yield

    # -------------------------------------------------------------------
    # SHUTDOWN
    # -------------------------------------------------------------------

    await engine.dispose()

    logger.info("app_shutdown")


# ---------------------------------------------------------------------------
# Security headers middleware
# ---------------------------------------------------------------------------

class SecurityHeadersMiddleware(BaseHTTPMiddleware):

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint
    ) -> Response:

        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"

        # Allow the KB to be embedded in our own frontend iframe
        if not request.url.path.startswith("/knowledge-base"):
            response.headers["X-Frame-Options"] = "DENY"

        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains; preload"
        )

        return response


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:

    app = FastAPI(
        title="CIQ v13 Backend",
        version="1.0.0",
        description="Controls Internal Quality — audit management API",
        lifespan=lifespan,
    )

    # -------------------------------------------------------------------
    # CORS
    # -------------------------------------------------------------------

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=[
            "GET",
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
            "OPTIONS"
        ],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Request-ID",
            "Idempotency-Key"
        ],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )

    # -------------------------------------------------------------------
    # Security Headers
    # -------------------------------------------------------------------

    app.add_middleware(
        SecurityHeadersMiddleware
    )

    # -------------------------------------------------------------------
    # Rate Limiting
    # -------------------------------------------------------------------

    from app.middleware.rate_limit import (
        RateLimitMiddleware
    )

    app.add_middleware(
        RateLimitMiddleware,
        max_requests=10,
        window_seconds=60
    )

    # -------------------------------------------------------------------
    # Request Logging
    # -------------------------------------------------------------------

    from app.middleware.request_logging import (
        RequestLoggingMiddleware
    )

    app.add_middleware(
        RequestLoggingMiddleware
    )

    # -------------------------------------------------------------------
    # Exception Handlers
    # -------------------------------------------------------------------

    register_exception_handlers(app)

    # -------------------------------------------------------------------
    # Prometheus Metrics
    # -------------------------------------------------------------------

    Instrumentator().instrument(app).expose(
        app,
        endpoint="/metrics"
    )

    # -------------------------------------------------------------------
    # ROUTERS
    # -------------------------------------------------------------------

    from app.api.endpoints.auth import (
        router as auth_router
    )

    from app.api.endpoints.clients import (
        router as clients_router
    )

    from app.api.endpoints.users import (
        router as users_router
    )

    from app.api.endpoints.versions import (
        router as versions_router
    )

    app.include_router(
        auth_router,
        prefix="/api/v1/auth",
        tags=["Auth"]
    )

    app.include_router(
        users_router,
        prefix="/api/v1/users",
        tags=["Users"]
    )

    app.include_router(
        clients_router,
        prefix="/api/v1/clients",
        tags=["Clients"]
    )

    app.include_router(
        versions_router,
        prefix="/api/v1/versions",
        tags=["Versions"]
    )

    # -------------------------------------------------------------------
    # CONTROL TESTING
    # -------------------------------------------------------------------

    from app.api.endpoints.control_testing import (
        router as control_tests_router
    )

    app.include_router(
        control_tests_router,
        prefix="/api/v1/control-testing",
        tags=["Control Testing"]
    )

    # -------------------------------------------------------------------
    # OTHER ROUTERS
    # -------------------------------------------------------------------

    from app.api.endpoints.controls import (
        router as controls_router
    )

    from app.api.endpoints.review_cycles import (
        router as review_cycles_router
    )

    from app.api.endpoints.evidence import (
        router as evidence_router
    )

    from app.api.endpoints.test_logs import (
        router as test_logs_router
    )

    app.include_router(
        review_cycles_router,
        prefix="/api/v1/review-cycles",
        tags=["Review Cycles"]
    )

    app.include_router(
        controls_router,
        prefix="/api/v1/controls",
        tags=["Controls"]
    )

    app.include_router(
        evidence_router,
        prefix="/api/v1/evidence",
        tags=["Evidence"]
    )

    app.include_router(
        test_logs_router,
        prefix="/api/v1/test-logs",
        tags=["Test Logs"]
    )

    from app.api.endpoints.reports import (
        router as reports_router
    )

    app.include_router(
        reports_router,
        prefix="/api/v1/reports",
        tags=["Reports"]
    )

    from app.api.endpoints.kb import (
        router as kb_router
    )

    app.include_router(
        kb_router,
        prefix="/api/v1/kb",
        tags=["Knowledge Base"]
    )

    # -------------------------------------------------------------------
    # KNOWLEDGE BASE — static Quartz-compiled site
    # -------------------------------------------------------------------

    import pathlib

    _kb_path = pathlib.Path(__file__).parent / "static" / "kb"
    _kb_path.mkdir(parents=True, exist_ok=True)

    app.mount(
        "/knowledge-base",
        StaticFiles(directory=str(_kb_path), html=True),
        name="knowledge_base",
    )

    # -------------------------------------------------------------------
    # HEALTH CHECK
    # -------------------------------------------------------------------

    @app.get("/health", tags=["Health"])
    async def health_check() -> dict[str, Any]:

        db_status = "connected"
        storage_status = "connected"

        # ---------------------------------------------------------------
        # DATABASE CHECK
        # ---------------------------------------------------------------

        try:

            from sqlalchemy import text

            from app.db.session import (
                async_session_maker
            )

            async with async_session_maker() as session:

                await session.execute(
                    text("SELECT 1")
                )

        except Exception:

            db_status = "disconnected"

        # ---------------------------------------------------------------
        # STORAGE CHECK
        # ---------------------------------------------------------------

        if settings.STORAGE_BACKEND == "local":

            pass

        else:

            try:

                from azure.storage.blob import (
                    BlobServiceClient
                )

                client = (
                    BlobServiceClient
                    .from_connection_string(
                        settings
                        .AZURE_STORAGE_CONNECTION_STRING
                    )
                )

                client.get_account_information()

            except Exception:

                storage_status = "disconnected"

        # ---------------------------------------------------------------
        # FINAL STATUS
        # ---------------------------------------------------------------

        status = (
            "ok"
            if db_status == "connected"
            and storage_status == "connected"
            else "degraded"
        )

        return {
            "status": status,
            "db": db_status,
            "storage": storage_status,
            "storage_backend": settings.STORAGE_BACKEND,
        }

    return app


# ---------------------------------------------------------------------------
# FastAPI Instance
# ---------------------------------------------------------------------------

app = create_app()