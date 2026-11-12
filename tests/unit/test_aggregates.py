"""Aggregation math and JSON-extraction tests."""

from __future__ import annotations

import pytest

from evalgate.metrics.jsonutil import JsonExtractionError, extract_json, extract_json_object
from evalgate.models.result import CaseResult, MetricResult
from evalgate.runner.aggregates import (
    nearest_rank_percentile,
    summarize,
    wilson_interval,
)


def test_wilson_bounds_at_extremes() -> None:
    low, high = wilson_interval(0, 10)
    assert low == 0.0
    assert high == pytest.approx(0.2775, abs=1e-4)

    low, high = wilson_interval(10, 10)
    assert low == pytest.approx(0.7225, abs=1e-4)
    assert high == pytest.approx(1.0)


def test_wilson_midpoint() -> None:
    low, high = wilson_interval(5, 10)
    assert low == pytest.approx(0.2366, abs=1e-4)
    assert high == pytest.approx(0.7634, abs=1e-4)


def test_wilson_zero_total() -> None:
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_wilson_rejects_invalid_successes() -> None:
    with pytest.raises(ValueError, match="between"):
        wilson_interval(11, 10)


def test_nearest_rank_percentile() -> None:
    values = list(range(1, 21))
    assert nearest_rank_percentile(values, 95) == 19
    assert nearest_rank_percentile([42], 95) == 42
    assert nearest_rank_percentile([], 95) == 0


def test_nearest_rank_rejects_bad_percentile() -> None:
    with pytest.raises(ValueError):
        nearest_rank_percentile([1], 0)


def test_summarize_counts_and_rates() -> None:
    cases = [
        CaseResult(
            case_id="a",
            passed=True,
            metrics=[MetricResult(metric="exact_match", score=1, passed=True)],
        ),
        CaseResult(
            case_id="b",
            passed=False,
            metrics=[MetricResult(metric="exact_match", score=0, passed=False)],
        ),
        CaseResult(case_id="c", passed=False, error="provider_error: boom"),
    ]
    summary = summarize(cases)
    assert summary.total == 3
    assert summary.passed == 1
    assert summary.failed == 1
    assert summary.errors == 1
    assert summary.pass_rate == pytest.approx(1 / 3)
    assert summary.metric_pass_rates == {"exact_match": 0.5}


def test_extract_json_variants() -> None:
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('prose {"a": 1} more') == {"a": 1}


def test_extract_json_rejects_missing_json() -> None:
    with pytest.raises(JsonExtractionError):
        extract_json("no json here")


def test_extract_json_object_requires_object() -> None:
    with pytest.raises(JsonExtractionError, match="not an object"):
        extract_json_object("[1]")
