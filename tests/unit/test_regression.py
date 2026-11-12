"""Regression rule truth table."""

from __future__ import annotations

import pytest

from evalgate.models.result import RegressionResult
from evalgate.runner.regression import Baseline, evaluate_regression


def _baseline(
    pass_rate: float = 0.9,
    low: float = 0.85,
    high: float = 0.95,
    total: int = 100,
) -> Baseline:
    return Baseline(
        label="main",
        suite_name="s",
        pass_rate=pass_rate,
        wilson_low=low,
        wilson_high=high,
        total=total,
    )


def _evaluate(
    *,
    baseline: Baseline | None = None,
    current: float = 0.8,
    low: float = 0.70,
    high: float = 0.88,
    total: int = 100,
    max_drop: float = 0.03,
    min_cases: int = 10,
) -> RegressionResult:
    return evaluate_regression(
        baseline=baseline or _baseline(),
        current_pass_rate=current,
        current_wilson_low=low,
        current_wilson_high=high,
        current_total=total,
        max_pass_rate_drop=max_drop,
        min_cases=min_cases,
    )


def test_drop_below_threshold_is_not_regression() -> None:
    result = _evaluate(current=0.88)
    assert not result.is_regression
    assert "within the allowed" in result.reason


def test_drop_at_threshold_is_not_regression() -> None:
    result = _evaluate(current=0.87)
    assert not result.is_regression


def test_drop_beyond_threshold_but_overlapping_intervals_is_noise() -> None:
    result = _evaluate(current=0.80, low=0.70, high=0.88)
    assert not result.is_regression
    assert result.intervals_overlap
    assert "overlap" in result.reason


def test_drop_beyond_threshold_with_separated_intervals_is_regression() -> None:
    result = _evaluate(current=0.60, low=0.50, high=0.70)
    assert result.is_regression
    assert not result.intervals_overlap
    assert result.drop == pytest.approx(0.30)


def test_improvement_is_not_regression() -> None:
    result = _evaluate(current=0.95, low=0.90, high=0.99)
    assert not result.is_regression
    assert result.drop < 0


def test_equal_pass_rate_is_not_regression() -> None:
    result = _evaluate(current=0.90, low=0.85, high=0.95)
    assert not result.is_regression


def test_small_sample_is_never_a_regression() -> None:
    result = _evaluate(
        baseline=_baseline(pass_rate=1.0, low=0.9, high=1.0, total=40),
        current=0.0,
        low=0.0,
        high=0.3,
        total=5,
    )
    assert not result.is_regression
    assert not result.sample_size_ok
    assert "small sample" in result.reason


def test_small_baseline_is_never_a_regression() -> None:
    result = _evaluate(
        baseline=_baseline(pass_rate=1.0, low=0.9, high=1.0, total=3),
        current=0.0,
        low=0.0,
        high=0.3,
        total=100,
    )
    assert not result.is_regression
    assert not result.sample_size_ok
