"""ARQ worker settings.

Run with: ``uv run arq evalgate.worker.settings.WorkerSettings``.
"""

from __future__ import annotations

from typing import Any, ClassVar

from arq.connections import RedisSettings

from evalgate.config import get_settings
from evalgate.storage.db import create_engine, create_session_factory
from evalgate.storage.repository import RunRepository
from evalgate.worker.tasks import run_suite_job

_settings = get_settings()


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    ctx["settings"] = settings
    ctx["engine"] = engine
    ctx["repository"] = RunRepository(create_session_factory(engine))


async def shutdown(ctx: dict[str, Any]) -> None:
    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()


class WorkerSettings:
    functions: ClassVar[list[Any]] = [run_suite_job]
    redis_settings = RedisSettings.from_dsn(_settings.redis_url)
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 4
    job_timeout = 900
    keep_result = 3600
