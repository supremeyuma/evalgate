"""Aggregation math: Wilson intervals, nearest-rank p95, and run summaries."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence

from evalgate.models.result import CaseResult, RunSummary

Z_95 = 1.959963984540054


def wilson_interval(successes: int, total: int, *, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Hand-rolled and unit-tested so the regression gate does not depend on a stats package.
    """

    if total <= 0:
        return (0.0, 1.0)
    if successes < 0 or successes > total:
        message = "successes must be between 0 and total"
        raise ValueError(message)

    proportion = successes / total
    denominator = 1.0 + (z * z) / total
    center = (proportion + (z * z) / (2.0 * total)) / denominator
    margin = (
        z
        * math.sqrt(proportion * (1.0 - proportion) / total + (z * z) / (4.0 * total * total))
        / denominator
    )
    return (max(0.0, center - margin), min(1.0, center + margin))


def nearest_rank_percentile(values: Sequence[int], percentile: float) -> int:
    """Nearest-rank percentile, as documented in the README.

    ``p95`` of 10 samples is the 10th smallest (index ``ceil(0.95 * 10) - 1 = 9``).
    """

    if not values:
        return 0
    if not 0 < percentile <= 100:
        message = "percentile must be in (0, 100]"
        raise ValueError(message)
    ordered = sorted(values)
    rank = math.ceil(percentile / 100 * len(ordered))
    index = min(max(rank - 1, 0), len(ordered) - 1)
    return ordered[index]


def summarize(cases: Sequence[CaseResult]) -> RunSummary:
    """Build the aggregate summary for a run."""

    total = len(cases)
    passed = sum(1 for case in cases if case.passed)
    errors = sum(1 for case in cases if case.error is not None)
    failed = total - passed - errors
    low, high = wilson_interval(passed, total)

    metric_counts: Counter[str] = Counter()
    metric_passes: Counter[str] = Counter()
    for case in cases:
        for metric in case.metrics:
            metric_counts[metric.metric] += 1
            if metric.passed:
                metric_passes[metric.metric] += 1

    metric_pass_rates = {name: metric_passes[name] / count for name, count in metric_counts.items()}

    return RunSummary(
        total=total,
        passed=passed,
        failed=failed,
        errors=errors,
        pass_rate=(passed / total) if total else 0.0,
        wilson_low=low,
        wilson_high=high,
        cost_usd=sum(case.cost_usd for case in cases),
        p95_latency_ms=nearest_rank_percentile([case.latency_ms for case in cases], 95.0),
        metric_pass_rates=metric_pass_rates,
    )
