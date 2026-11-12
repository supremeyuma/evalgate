"""Exact-match metric."""

from __future__ import annotations

import re

from evalgate.metrics.base import clip
from evalgate.models.case import Case
from evalgate.models.result import MetricResult
from evalgate.models.suite import ExactMatchSpec
from evalgate.providers.base import Completion

_WHITESPACE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WHITESPACE.sub(" ", text.strip()).lower()


def evaluate(spec: ExactMatchSpec, case: Case, completion: Completion) -> MetricResult:
    if case.expected is None:
        return MetricResult(
            metric=spec.type,
            score=0.0,
            passed=False,
            detail="case has no expected value for exact_match",
        )

    expected = case.expected
    actual = completion.text
    if spec.normalize:
        expected = _normalize(expected)
        actual = _normalize(actual)

    passed = actual == expected
    detail = "match" if passed else f"expected {clip(expected)!r}, got {clip(actual)!r}"
    return MetricResult(
        metric=spec.type, score=1.0 if passed else 0.0, passed=passed, detail=detail
    )
