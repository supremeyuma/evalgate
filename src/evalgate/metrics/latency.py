"""Latency budget metric."""

from __future__ import annotations

from evalgate.models.case import Case
from evalgate.models.result import MetricResult
from evalgate.models.suite import LatencySpec, Limits
from evalgate.providers.base import Completion


def evaluate(
    spec: LatencySpec,
    case: Case,
    completion: Completion,
    limits: Limits,
) -> MetricResult:
    threshold = spec.max if spec.max is not None else limits.max_p95_latency_ms
    if threshold is None:
        return MetricResult(
            metric=spec.type,
            score=1.0,
            passed=True,
            detail=f"no latency limit configured (observed {completion.latency_ms}ms)",
        )

    passed = completion.latency_ms <= threshold
    return MetricResult(
        metric=spec.type,
        score=1.0 if passed else 0.0,
        passed=passed,
        detail=f"{completion.latency_ms}ms vs limit {threshold}ms",
    )
