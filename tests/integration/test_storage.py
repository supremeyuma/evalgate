"""Repository lifecycle, idempotency, and baseline resolution."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from evalgate.models.result import RunReport
from evalgate.providers.mock import MockProvider
from evalgate.runner.engine import RunOptions, run_suite
from evalgate.storage.models import ResultRow
from evalgate.storage.repository import RunRepository


async def _report(make_suite: Any) -> tuple[RunReport, str, Path]:
    loaded = make_suite(
        cases=[
            {"id": "c00", "input": "one", "expected": "ok"},
            {"id": "c01", "input": "two", "expected": "ok"},
        ]
    )
    report = await run_suite(loaded, MockProvider(), options=RunOptions(mode="mock"))
    return report, loaded.path.read_text(encoding="utf-8"), loaded.path


async def _result_count(
    session_factory: async_sessionmaker[AsyncSession], run_id: uuid.UUID
) -> int:
    async with session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(ResultRow).where(ResultRow.run_id == run_id)
        )
    return int(count or 0)


async def test_save_and_read_report(repository: RunRepository, make_suite: Any) -> None:
    report, yaml, suite_path = await _report(make_suite)
    run_id = await repository.save_report(
        report,
        suite_yaml=yaml,
        suite_path=str(suite_path),
        mode="mock",
    )
    stored = await repository.get_run(run_id)
    assert stored is not None
    assert stored.status == "passed"
    restored = await repository.get_report(run_id)
    assert restored is not None
    assert restored.summary.total == 2
    assert restored.suite_name == report.suite_name


async def test_record_results_is_idempotent(
    repository: RunRepository,
    session_factory: async_sessionmaker[AsyncSession],
    make_suite: Any,
) -> None:
    report, yaml, suite_path = await _report(make_suite)
    suite_id = await repository.get_or_create_suite(report.suite_name, yaml)
    run_id = await repository.create_run(suite_id=suite_id, suite_path=str(suite_path), mode="mock")
    await repository.record_results(run_id, report.cases)
    first = await _result_count(session_factory, run_id)
    await repository.record_results(run_id, report.cases)
    second = await _result_count(session_factory, run_id)
    assert first == second == 2


async def test_exit_code_maps_to_status(repository: RunRepository, make_suite: Any) -> None:
    report, yaml, suite_path = await _report(make_suite)
    failed = report.model_copy(update={"exit_code": 1})
    failed_id = await repository.save_report(
        failed, suite_yaml=yaml, suite_path=str(suite_path), mode="mock"
    )
    errored = report.model_copy(update={"exit_code": 3})
    errored_id = await repository.save_report(
        errored, suite_yaml=yaml, suite_path=str(suite_path), mode="mock"
    )
    assert (await repository.get_run(failed_id)).status == "failed"  # type: ignore[union-attr]
    assert (await repository.get_run(errored_id)).status == "error"  # type: ignore[union-attr]


async def test_baseline_by_git_ref(repository: RunRepository, make_suite: Any) -> None:
    report, yaml, suite_path = await _report(make_suite)
    suite_id = await repository.get_or_create_suite(report.suite_name, yaml)
    main_run = await repository.save_report(
        report,
        suite_yaml=yaml,
        suite_path=str(suite_path),
        mode="mock",
        git_ref="main",
    )
    await repository.save_report(
        report,
        suite_yaml=yaml,
        suite_path=str(suite_path),
        mode="mock",
        git_ref="feature",
    )
    baseline = await repository.fetch_baseline(suite_id, git_ref="main")
    assert baseline is not None
    assert baseline.id == main_run
    explicit = await repository.fetch_baseline(suite_id, run_id=main_run)
    assert explicit is not None
    assert explicit.id == main_run


async def test_list_runs_returns_latest_first(repository: RunRepository, make_suite: Any) -> None:
    report, yaml, suite_path = await _report(make_suite)
    for _ in range(3):
        await repository.save_report(
            report, suite_yaml=yaml, suite_path=str(suite_path), mode="mock"
        )
    runs = await repository.list_runs(limit=10)
    assert len(runs) == 3
    assert all(run.report is not None for run in runs)
