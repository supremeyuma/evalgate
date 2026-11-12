"""Baseline loading and the regression rule.

A drop counts as a regression only when **all** of these hold:

1. the current run has at least ``regression.min_cases`` cases,
2. the pass rate dropped by more than ``regression.max_pass_rate_drop``, and
3. the baseline's Wilson lower bound is above the current Wilson upper bound, i.e. the
   intervals do not overlap in the direction of a decline.

The interval condition keeps a 3-point drop on 12 cases from failing a PR on noise.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from evalgate.models.result import RegressionResult, RunReport


class Baseline(BaseModel):
    """The parts of a previous run needed for comparison."""

    model_config = ConfigDict(extra="forbid")

    label: str
    suite_name: str
    pass_rate: float
    wilson_low: float
    wilson_high: float
    total: int


def load_baseline_report(path: str | Path) -> Baseline:
    """Read a previously written JSON report as a baseline."""

    baseline_path = Path(path)
    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    report = RunReport.model_validate(payload)
    return Baseline(
        label=baseline_path.name,
        suite_name=report.suite_name,
        pass_rate=report.summary.pass_rate,
        wilson_low=report.summary.wilson_low,
        wilson_high=report.summary.wilson_high,
        total=report.summary.total,
    )


def evaluate_regression(
    *,
    baseline: Baseline,
    current_pass_rate: float,
    current_wilson_low: float,
    current_wilson_high: float,
    current_total: int,
    max_pass_rate_drop: float,
    min_cases: int,
) -> RegressionResult:
    """Apply the documented regression rule."""

    drop = baseline.pass_rate - current_pass_rate
    sample_size_ok = current_total >= min_cases and baseline.total >= min_cases
    intervals_overlap = current_wilson_high >= baseline.wilson_low

    if not sample_size_ok:
        return RegressionResult(
            is_regression=False,
            reason=(
                f"small sample: need at least {min_cases} cases in both runs "
                f"(baseline {baseline.total}, current {current_total})"
            ),
            baseline_pass_rate=baseline.pass_rate,
            current_pass_rate=current_pass_rate,
            drop=drop,
            max_pass_rate_drop=max_pass_rate_drop,
            intervals_overlap=intervals_overlap,
            sample_size_ok=False,
        )

    if drop <= max_pass_rate_drop:
        return RegressionResult(
            is_regression=False,
            reason=(f"drop {drop:.3f} is within the allowed {max_pass_rate_drop:.3f}"),
            baseline_pass_rate=baseline.pass_rate,
            current_pass_rate=current_pass_rate,
            drop=drop,
            max_pass_rate_drop=max_pass_rate_drop,
            intervals_overlap=intervals_overlap,
            sample_size_ok=True,
        )

    if intervals_overlap:
        return RegressionResult(
            is_regression=False,
            reason=(
                f"drop {drop:.3f} exceeds the threshold but Wilson 95% intervals overlap "
                f"(baseline lower {baseline.wilson_low:.3f} <= current upper "
                f"{current_wilson_high:.3f}); treat as noise"
            ),
            baseline_pass_rate=baseline.pass_rate,
            current_pass_rate=current_pass_rate,
            drop=drop,
            max_pass_rate_drop=max_pass_rate_drop,
            intervals_overlap=True,
            sample_size_ok=True,
        )

    return RegressionResult(
        is_regression=True,
        reason=(
            f"pass rate fell {drop:.3f} (>{max_pass_rate_drop:.3f}) and the Wilson 95% "
            f"intervals do not overlap: baseline lower {baseline.wilson_low:.3f} > "
            f"current upper {current_wilson_high:.3f}"
        ),
        baseline_pass_rate=baseline.pass_rate,
        current_pass_rate=current_pass_rate,
        drop=drop,
        max_pass_rate_drop=max_pass_rate_drop,
        intervals_overlap=False,
        sample_size_ok=True,
    )
