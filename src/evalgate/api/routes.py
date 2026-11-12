"""Run endpoints. The API is a demo convenience; the CLI remains primary."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from evalgate.api.deps import get_app_settings, get_repository, require_api_key
from evalgate.config import Settings
from evalgate.judges.cache import build_judge_cache
from evalgate.models.loader import SuiteLoadError, load_suite
from evalgate.providers import ProviderConfigError
from evalgate.report import render_html
from evalgate.runner.service import execute_suite, resolve_inline_suite
from evalgate.storage.repository import RunRepository

router = APIRouter(prefix="/v1", tags=["runs"])


class RunRequest(BaseModel):
    """Start a run from a suite path or inline YAML."""

    model_config = ConfigDict(extra="forbid")

    suite: str | None = Field(default=None, description="Suite YAML path on the server.")
    suite_yaml: str | None = Field(
        default=None, description="Inline suite YAML; assets resolve in working_directory."
    )
    working_directory: str | None = Field(
        default=None, description="Base directory for inline YAML assets."
    )
    git_ref: str | None = None
    commit_sha: str | None = None
    baseline_run_id: uuid.UUID | None = None
    mock: bool = False
    concurrency: int = Field(default=5, ge=1, le=50)

    @model_validator(mode="after")
    def _one_source(self) -> RunRequest:
        if (self.suite is None) == (self.suite_yaml is None):
            message = "provide exactly one of suite or suite_yaml"
            raise ValueError(message)
        return self


class RunCreated(BaseModel):
    id: uuid.UUID
    suite_name: str
    status: str
    mode: str
    pass_rate: float
    exit_code: int


def _run_payload(row: Any) -> dict[str, Any]:
    report = row.report or {}
    return {
        "id": str(row.id),
        "status": row.status,
        "mode": row.mode,
        "suite_path": row.suite_path,
        "commit_sha": row.commit_sha,
        "git_ref": row.git_ref,
        "baseline_run_id": str(row.baseline_run_id) if row.baseline_run_id else None,
        "pass_rate": row.pass_rate,
        "cost_usd": row.cost_usd,
        "p95_latency_ms": row.p95_latency_ms,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "summary": report.get("summary"),
        "limit_breaches": report.get("limit_breaches", []),
        "baseline": report.get("baseline"),
    }


@router.post(
    "/runs",
    status_code=status.HTTP_201_CREATED,
    response_model=RunCreated,
    dependencies=[Depends(require_api_key)],
)
async def create_run(
    body: RunRequest,
    request: Request,
    repository: Annotated[RunRepository, Depends(get_repository)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> RunCreated:
    inline_path: Path | None = None
    if body.suite_yaml is not None:
        try:
            inline_path = resolve_inline_suite(body.suite_yaml, body.working_directory)
        except (OSError, ValueError) as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
            ) from error
        suite_path = inline_path
    else:
        suite_path = Path(body.suite or "").expanduser()  # noqa: ASYNC240 - tiny stat
        if not suite_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"suite file not found: {suite_path}",
            )

    cache: Any = None
    try:
        try:
            loaded = load_suite(suite_path)
        except SuiteLoadError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
            ) from error

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
                mock=body.mock,
                git_ref=body.git_ref,
                commit_sha=body.commit_sha,
                baseline_run_id=body.baseline_run_id,
                concurrency=body.concurrency,
                cache=cache,
            )
        except ProviderConfigError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
            ) from error
    finally:
        if cache is not None:
            await cache.aclose()
        if inline_path is not None:
            inline_path.unlink(missing_ok=True)

    row = await repository.get_run(run_id)
    run_status = row.status if row is not None else "unknown"
    return RunCreated(
        id=run_id,
        suite_name=report.suite_name,
        status=run_status,
        mode=report.mode,
        pass_rate=report.summary.pass_rate,
        exit_code=report.exit_code,
    )


@router.get(
    "/runs",
    dependencies=[Depends(require_api_key)],
)
async def list_runs(
    repository: Annotated[RunRepository, Depends(get_repository)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[dict[str, Any]]:
    rows = await repository.list_runs(limit=limit)
    return [_run_payload(row) for row in rows]


@router.get(
    "/runs/{run_id}",
    dependencies=[Depends(require_api_key)],
)
async def get_run(
    run_id: uuid.UUID,
    repository: Annotated[RunRepository, Depends(get_repository)],
) -> dict[str, Any]:
    row = await repository.get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")
    return _run_payload(row)


@router.get(
    "/runs/{run_id}/report.json",
    dependencies=[Depends(require_api_key)],
)
async def get_run_report_json(
    run_id: uuid.UUID,
    repository: Annotated[RunRepository, Depends(get_repository)],
) -> JSONResponse:
    row = await repository.get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")
    if row.report is None:
        raise HTTPException(status_code=409, detail="run has no report yet")
    return JSONResponse(content=row.report)


@router.get(
    "/runs/{run_id}/report.html",
    response_class=HTMLResponse,
    dependencies=[Depends(require_api_key)],
)
async def get_run_report_html(
    run_id: uuid.UUID,
    repository: Annotated[RunRepository, Depends(get_repository)],
) -> Response:
    report = await repository.get_report(run_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    return HTMLResponse(content=render_html(report))
