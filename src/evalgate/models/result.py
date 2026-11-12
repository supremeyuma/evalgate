"""Result models shared by the runner, reports, and API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RunMode = Literal["mock", "live"]


class MetricResult(BaseModel):
    """The verdict of one metric on one case."""

    model_config = ConfigDict(extra="forbid")

    metric: str
    score: float = Field(ge=0.0, le=1.0)
    passed: bool
    detail: str | None = None
    judge_output: dict[str, Any] | None = None
    cache_hit: bool = False
    judge_cost_usd: float = 0.0
    judge_saved_usd: float = 0.0


class CaseResult(BaseModel):
    """Everything that happened for one case."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    passed: bool
    response: str = ""
    latency_ms: int = 0
    cost_usd: float = 0.0
    metrics: list[MetricResult] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    error: str | None = None


class RunSummary(BaseModel):
    """Aggregates over all cases in a run."""

    model_config = ConfigDict(extra="forbid")

    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    pass_rate: float = 0.0
    wilson_low: float = 0.0
    wilson_high: float = 1.0
    cost_usd: float = 0.0
    p95_latency_ms: int = 0
    metric_pass_rates: dict[str, float] = Field(default_factory=dict)
    judge_calls: int = 0
    judge_cache_hits: int = 0
    judge_cost_usd: float = 0.0
    judge_saved_usd: float = 0.0


class LimitBreach(BaseModel):
    """A hard limit that the run exceeded."""

    model_config = ConfigDict(extra="forbid")

    limit: str
    threshold: float
    actual: float
    message: str


class RegressionResult(BaseModel):
    """The outcome of comparing the run with a baseline."""

    model_config = ConfigDict(extra="forbid")

    is_regression: bool
    reason: str
    baseline_pass_rate: float
    current_pass_rate: float
    drop: float
    max_pass_rate_drop: float
    intervals_overlap: bool
    sample_size_ok: bool


class BaselineComparison(BaseModel):
    """Baseline metadata plus the regression verdict."""

    model_config = ConfigDict(extra="forbid")

    label: str
    baseline_pass_rate: float
    current_pass_rate: float
    delta: float
    regression: RegressionResult


class RunReport(BaseModel):
    """The complete, serializable result of one suite run."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    suite_name: str
    provider: str
    model_name: str
    mode: RunMode
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    summary: RunSummary
    cases: list[CaseResult] = Field(default_factory=list)
    limit_breaches: list[LimitBreach] = Field(default_factory=list)
    baseline: BaselineComparison | None = None
    exit_code: int = 0
