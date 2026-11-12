"""Persistence layer for suites, runs, results, and baseline lookup."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from evalgate.models.result import CaseResult, RunReport
from evalgate.runner.regression import Baseline
from evalgate.storage.models import ResultRow, RunRow, SuiteRow

_TERMINAL_STATUSES = ("passed", "failed")


class RunRepository:
    """All database access for runs and results goes through this class."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_or_create_suite(self, name: str, yaml_text: str) -> uuid.UUID:
        async with self._session_factory() as session:
            existing = await session.scalar(
                select(SuiteRow)
                .where(SuiteRow.name == name, SuiteRow.yaml == yaml_text)
                .order_by(SuiteRow.created_at.desc())
                .limit(1)
            )
            if existing is not None:
                return existing.id
            row = SuiteRow(name=name, yaml=yaml_text)
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row.id

    async def create_run(
        self,
        *,
        suite_id: uuid.UUID,
        suite_path: str,
        mode: str,
        commit_sha: str | None = None,
        git_ref: str | None = None,
        baseline_run_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        async with self._session_factory() as session:
            row = RunRow(
                suite_id=suite_id,
                suite_path=suite_path,
                mode=mode,
                status="running",
                commit_sha=commit_sha,
                git_ref=git_ref,
                baseline_run_id=baseline_run_id,
                started_at=datetime.now(UTC),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row.id

    async def set_status(self, run_id: uuid.UUID, status: str) -> None:
        async with self._session_factory() as session:
            row = await session.get(RunRow, run_id)
            if row is not None:
                row.status = status
                await session.commit()

    async def record_results(self, run_id: uuid.UUID, cases: Sequence[CaseResult]) -> None:
        """Insert one row per metric; retries upsert instead of duplicating."""

        values: list[dict[str, object]] = []
        for case in cases:
            if case.error is not None and not case.metrics:
                values.append(
                    {
                        "run_id": run_id,
                        "case_id": case.case_id,
                        "metric": "__error__",
                        "score": 0.0,
                        "passed": False,
                        "latency_ms": case.latency_ms,
                        "cost_usd": case.cost_usd,
                        "detail": case.error,
                        "judge_output": None,
                        "response": case.response,
                    }
                )
                continue
            for metric in case.metrics:
                values.append(
                    {
                        "run_id": run_id,
                        "case_id": case.case_id,
                        "metric": metric.metric,
                        "score": metric.score,
                        "passed": metric.passed,
                        "latency_ms": case.latency_ms,
                        "cost_usd": case.cost_usd,
                        "detail": metric.detail,
                        "judge_output": metric.judge_output,
                        "response": case.response,
                    }
                )
        if not values:
            return

        statement = pg_insert(ResultRow).values(values)
        statement = statement.on_conflict_do_update(
            index_elements=[ResultRow.run_id, ResultRow.case_id, ResultRow.metric],
            set_={
                "score": statement.excluded.score,
                "passed": statement.excluded.passed,
                "latency_ms": statement.excluded.latency_ms,
                "cost_usd": statement.excluded.cost_usd,
                "detail": statement.excluded.detail,
                "judge_output": statement.excluded.judge_output,
                "response": statement.excluded.response,
            },
        )
        async with self._session_factory() as session:
            await session.execute(statement)
            await session.commit()

    async def finalize_run(self, run_id: uuid.UUID, report: RunReport) -> None:
        status = {0: "passed", 1: "failed"}.get(report.exit_code, "error")
        async with self._session_factory() as session:
            row = await session.get(RunRow, run_id)
            if row is None:
                return
            row.status = status
            row.pass_rate = report.summary.pass_rate
            row.wilson_low = report.summary.wilson_low
            row.wilson_high = report.summary.wilson_high
            row.total_cases = report.summary.total
            row.cost_usd = report.summary.cost_usd
            row.p95_latency_ms = report.summary.p95_latency_ms
            row.finished_at = datetime.now(UTC)
            row.report = report.model_dump(mode="json")
            await session.commit()

    async def save_report(
        self,
        report: RunReport,
        *,
        suite_yaml: str,
        suite_path: str,
        mode: str,
        commit_sha: str | None = None,
        git_ref: str | None = None,
        baseline_run_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """Convenience path: create the suite, run, results, and final row."""

        suite_id = await self.get_or_create_suite(report.suite_name, suite_yaml)
        run_id = await self.create_run(
            suite_id=suite_id,
            suite_path=suite_path,
            mode=mode,
            commit_sha=commit_sha,
            git_ref=git_ref,
            baseline_run_id=baseline_run_id,
        )
        await self.record_results(run_id, report.cases)
        await self.finalize_run(run_id, report)
        return run_id

    async def get_run(self, run_id: uuid.UUID) -> RunRow | None:
        async with self._session_factory() as session:
            return await session.get(RunRow, run_id)

    async def get_report(self, run_id: uuid.UUID) -> RunReport | None:
        row = await self.get_run(run_id)
        if row is None or row.report is None:
            return None
        return RunReport.model_validate(row.report)

    async def list_runs(self, *, limit: int = 20) -> list[RunRow]:
        async with self._session_factory() as session:
            result = await session.scalars(
                select(RunRow).order_by(RunRow.started_at.desc()).limit(limit)
            )
            return list(result)

    async def fetch_baseline(
        self,
        suite_id: uuid.UUID,
        *,
        git_ref: str | None = None,
        run_id: uuid.UUID | None = None,
    ) -> RunRow | None:
        """Explicit run id, else the latest terminal run for the same suite and ref."""

        async with self._session_factory() as session:
            if run_id is not None:
                return await session.get(RunRow, run_id)
            query = select(RunRow).where(
                RunRow.suite_id == suite_id,
                RunRow.status.in_(_TERMINAL_STATUSES),
                RunRow.report.is_not(None),
            )
            if git_ref is not None:
                query = query.where(RunRow.git_ref == git_ref)
            query = query.order_by(RunRow.started_at.desc()).limit(1)
            return await session.scalar(query)


def baseline_from_row(row: RunRow) -> Baseline:
    """Convert a stored run into the comparison object used by the regression rule."""

    return Baseline(
        label=f"run {str(row.id)[:8]}",
        suite_name=row.report.get("suite_name", "") if row.report else "",
        pass_rate=row.pass_rate or 0.0,
        wilson_low=row.wilson_low,
        wilson_high=row.wilson_high,
        total=row.total_cases,
    )
