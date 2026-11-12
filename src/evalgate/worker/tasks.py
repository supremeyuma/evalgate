"""ARQ job that executes a suite and persists the run."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from evalgate.config import get_settings
from evalgate.judges.cache import build_judge_cache
from evalgate.models.loader import load_suite
from evalgate.runner.service import execute_suite
from evalgate.storage.repository import RunRepository


async def run_suite_job(
    ctx: dict[str, Any],
    suite_path: str,
    *,
    mock: bool = False,
    git_ref: str | None = None,
    commit_sha: str | None = None,
    baseline_run_id: str | None = None,
    concurrency: int = 5,
) -> dict[str, Any]:
    """Run one suite from a filesystem path and return a compact job result."""

    settings = ctx.get("settings") or get_settings()
    repository: RunRepository = ctx["repository"]
    redis = ctx.get("redis")

    loaded = load_suite(Path(suite_path))

    async def progress(run_id: uuid.UUID, percent: int) -> None:
        if redis is not None:
            await redis.set(f"evalgate:progress:{run_id}", percent, ex=3600)

    cache = build_judge_cache(
        backend="postgres",
        cache_dir=settings.judge_cache_dir,
        database_url=settings.database_url,
    )
    try:
        run_id, report = await execute_suite(
            repository=repository,
            loaded=loaded,
            settings=settings,
            mock=mock,
            git_ref=git_ref,
            commit_sha=commit_sha,
            baseline_run_id=uuid.UUID(baseline_run_id) if baseline_run_id else None,
            concurrency=concurrency,
            cache=cache,
            progress=progress,
        )
    finally:
        await cache.aclose()

    return {
        "run_id": str(run_id),
        "status": "passed" if report.exit_code == 0 else "failed",
        "pass_rate": report.summary.pass_rate,
        "exit_code": report.exit_code,
    }
