"""FastAPI application factory with request-id logging and health endpoints."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from evalgate import __version__
from evalgate.api.routes import router
from evalgate.config import Settings, get_settings
from evalgate.storage.db import create_engine, create_session_factory
from evalgate.storage.repository import RunRepository

logger = logging.getLogger("evalgate.api")


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        context = getattr(record, "context", {})
        payload = {"level": record.levelname, "message": record.getMessage()}
        payload.update(context)
        return json.dumps(payload)


def _configure_logging() -> None:
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app; tests inject settings for an isolated database."""

    config = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        _configure_logging()
        engine = create_engine(config.database_url)
        app.state.settings = config
        app.state.engine = engine
        app.state.repository = RunRepository(create_session_factory(engine))
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(
        title="EvalGate API",
        version=__version__,
        description=(
            "Thin API over the EvalGate runner. The CLI is the primary interface; "
            "this exists for the compose demo and worker integration."
        ),
        lifespan=lifespan,
    )
    app.include_router(router)

    @app.middleware("http")
    async def request_logging(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request failed",
                extra={
                    "context": {
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "status": 500,
                        "duration_ms": int((time.perf_counter() - started) * 1000),
                    }
                },
            )
            raise
        response.headers["x-request-id"] = request_id
        logger.info(
            "request",
            extra={
                "context": {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                }
            },
        )
        return response

    @app.get("/healthz", tags=["health"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["health"])
    async def readyz(request: Request) -> JSONResponse:
        engine = request.app.state.engine
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "database unavailable"},
            )
        return JSONResponse(content={"status": "ready"})

    return app


app = create_app()
