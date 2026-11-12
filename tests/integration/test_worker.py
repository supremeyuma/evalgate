"""ARQ job execution against real Postgres and Redis."""

from __future__ import annotations

import uuid
from typing import Any

from evalgate.config import Settings
from evalgate.storage.repository import RunRepository
from evalgate.worker.tasks import run_suite_job


async def test_worker_runs_suite_and_reports_progress(
    repository: RunRepository,
    api_settings: Settings,
    redis_client: Any,
    make_suite: Any,
) -> None:
    loaded = make_suite(
        cases=[
            {"id": "c00", "input": "one", "expected": "ok"},
            {"id": "c01", "input": "two", "expected": "ok"},
        ]
    )
    ctx = {
        "repository": repository,
        "settings": api_settings,
        "redis": redis_client,
    }
    result = await run_suite_job(ctx, str(loaded.path), mock=True, git_ref="main")
    assert result["exit_code"] == 0
    assert result["pass_rate"] == 1.0

    run_id = uuid.UUID(str(result["run_id"]))
    progress = await redis_client.get(f"evalgate:progress:{run_id}")
    assert progress == b"100"

    row = await repository.get_run(run_id)
    assert row is not None
    assert row.status == "passed"
    assert row.git_ref == "main"
    report = await repository.get_report(run_id)
    assert report is not None
    assert report.summary.total == 2


async def test_worker_marks_error_when_suite_missing(
    repository: RunRepository,
    api_settings: Settings,
    redis_client: Any,
) -> None:
    import pytest

    with pytest.raises(Exception):  # noqa: B017 - loader error type is an implementation detail
        await run_suite_job(
            {"repository": repository, "settings": api_settings, "redis": redis_client},
            "does-not-exist.yaml",
            mock=True,
        )
