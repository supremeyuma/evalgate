"""Per-case cost budget metric."""

from __future__ import annotations

from decimal import Decimal

from evalgate.models.case import Case
from evalgate.models.result import MetricResult
from evalgate.models.suite import CostSpec, Limits
from evalgate.providers.base import Completion


def evaluate(
    spec: CostSpec,
    case: Case,
    completion: Completion,
    limits: Limits,
) -> MetricResult:
    threshold: Decimal | None
    threshold = spec.max if spec.max is not None else limits.max_cost_usd
    if threshold is None:
        return MetricResult(
            metric=spec.type,
            score=1.0,
            passed=True,
            detail=f"no cost limit configured (observed ${completion.cost_usd:.6f})",
        )

    passed = completion.cost_usd <= threshold
    return MetricResult(
        metric=spec.type,
        score=1.0 if passed else 0.0,
        passed=passed,
        detail=f"${completion.cost_usd:.6f} vs limit ${threshold:.6f}",
    )
