"""SQLAlchemy models for suites, runs, results, and the judge cache."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for every EvalGate table."""

    metadata = MetaData(naming_convention=_NAMING_CONVENTION)


class SuiteRow(Base):
    """A suite YAML document, versioned by content."""

    __tablename__ = "suites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), index=True)
    yaml: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RunRow(Base):
    """One execution of a suite."""

    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    suite_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suites.id", ondelete="CASCADE"), index=True
    )
    suite_path: Mapped[str] = mapped_column(String(1024))
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    git_ref: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    baseline_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    mode: Mapped[str] = mapped_column(String(8), default="live")
    pass_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    wilson_low: Mapped[float] = mapped_column(Float, default=0.0)
    wilson_high: Mapped[float] = mapped_column(Float, default=1.0)
    total_cases: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    p95_latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    report: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_runs_suite_started", "suite_id", "started_at"),)


class ResultRow(Base):
    """One metric verdict for one case in one run."""

    __tablename__ = "results"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
    case_id: Mapped[str] = mapped_column(String(128))
    metric: Mapped[str] = mapped_column(String(64))
    score: Mapped[float] = mapped_column(Float)
    passed: Mapped[bool] = mapped_column(Boolean)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    judge_output: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    response: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (
        UniqueConstraint("run_id", "case_id", "metric", name="uq_results_run_case_metric"),
    )


class JudgeCacheRow(Base):
    """Content-addressed judge verdict, keyed by response + rubric + model + prompt version."""

    __tablename__ = "judge_cache"

    hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    response_hash: Mapped[str] = mapped_column(String(64), index=True)
    rubric_hash: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128), index=True)
    score: Mapped[int] = mapped_column(Integer)
    rationale: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
