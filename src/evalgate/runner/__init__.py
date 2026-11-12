"""Runner: prompt rendering, bounded concurrency, aggregation, and regression."""

from __future__ import annotations

from evalgate.runner.aggregates import (
    nearest_rank_percentile,
    summarize,
    wilson_interval,
)
from evalgate.runner.engine import RunOptions, render_prompt, run_suite
from evalgate.runner.regression import (
    Baseline,
    evaluate_regression,
    load_baseline_report,
)

__all__ = [
    "Baseline",
    "RunOptions",
    "evaluate_regression",
    "load_baseline_report",
    "nearest_rank_percentile",
    "render_prompt",
    "run_suite",
    "summarize",
    "wilson_interval",
]
