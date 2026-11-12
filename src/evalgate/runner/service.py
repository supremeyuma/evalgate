"""Shared execution service used by the API and the ARQ worker."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from evalgate.config import Settings
from evalgate.judges.cache import JudgeCache
from evalgate.models.loader import LoadedSuite
from evalgate.models.result import RunReport
from evalgate.providers import build_provider
from evalgate.runner.engine import RunOptions, run_suite
from evalgate.runner.regression import Baseline
from evalgate.storage.repository import RunRepository, baseline_from_row

ProgressCallback = Callable[[uuid.UUID, int], Awaitable[None]]


async def _noop_progress(run_id: uuid.UUID, percent: int) -> None:
    return None


async def execute_suite(
    *,
    repository: RunRepository,
    loaded: LoadedSuite,
    settings: Settings,
    mock: bool,
    git_ref: str | None,
    commit_sha: str | None,
    baseline_run_id: uuid.UUID | None,
    concurrency: int,
    cache: JudgeCache,
    progress: ProgressCallback | None = None,
) -> tuple[uuid.UUID, RunReport]:
    """Create a run, execute it, persist results, and return the report.

    Every run row is created before provider calls so a crash leaves an inspectable
    ``error`` run rather than a orphan.
    """

    notify = progress or _noop_progress
    suite_path = loaded.path
    suite_yaml = suite_path.read_text(encoding="utf-8")
    suite_id = await repository.get_or_create_suite(loaded.suite.name, suite_yaml)

    baseline_row = None
    if baseline_run_id is not None:
        baseline_row = await repository.fetch_baseline(suite_id, run_id=baseline_run_id)
    elif git_ref is not None:
        baseline_row = await repository.fetch_baseline(suite_id, git_ref=git_ref)
    baseline: Baseline | None = (
        baseline_from_row(baseline_row) if baseline_row is not None else None
    )

    mode = "mock" if mock or loaded.suite.model.provider == "mock" else "live"
    run_id = await repository.create_run(
        suite_id=suite_id,
        suite_path=str(suite_path),
        mode=mode,
        commit_sha=commit_sha,
        git_ref=git_ref,
        baseline_run_id=baseline_row.id if baseline_row is not None else None,
    )
    await notify(run_id, 0)

    provider = build_provider(loaded.suite.model, force_mock=mock, settings=settings)
    try:
        report = await run_suite(
            loaded,
            provider,
            judge_model=settings.judge_model,
            options=RunOptions(
                concurrency=concurrency,
                case_timeout_s=settings.provider_timeout_s,
                mode=mode,
            ),
            baseline=baseline,
            cache=cache,
        )
    except Exception:
        await repository.set_status(run_id, "error")
        raise
    finally:
        await provider.aclose()

    await repository.record_results(run_id, report.cases)
    await repository.finalize_run(run_id, report)
    await notify(run_id, 100)
    return run_id, report


def resolve_inline_suite(yaml_text: str, working_directory: str | None) -> Path:
    """Write inline YAML next to its assets so relative paths resolve as usual."""

    base = Path(working_directory or ".").expanduser().resolve()
    if not base.is_dir():
        message = f"working directory does not exist: {base}"
        raise ValueError(message)
    suite_path = base / f".evalgate-inline-{uuid.uuid4().hex}.yaml"
    suite_path.write_text(yaml_text, encoding="utf-8", newline="\n")
    return suite_path
