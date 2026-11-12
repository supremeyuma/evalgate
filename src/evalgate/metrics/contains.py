"""Substring-presence metric."""

from __future__ import annotations

from evalgate.metrics.base import clip
from evalgate.models.case import Case
from evalgate.models.result import MetricResult
from evalgate.models.suite import ContainsSpec
from evalgate.providers.base import Completion


def evaluate(spec: ContainsSpec, case: Case, completion: Completion) -> MetricResult:
    values = [spec.value] if isinstance(spec.value, str) else spec.value
    haystack = completion.text.lower()
    present = [value for value in values if value.lower() in haystack]
    missing = [value for value in values if value.lower() not in haystack]

    if spec.mode == "all":
        passed = not missing
        score = len(present) / len(values) if values else 0.0
        detail = (
            "all required substrings present"
            if passed
            else f"missing {', '.join(repr(item) for item in missing)}"
        )
    else:
        passed = bool(present)
        score = 1.0 if passed else 0.0
        detail = (
            f"found {', '.join(repr(item) for item in present)}"
            if passed
            else f"none of {clip(', '.join(repr(item) for item in values))} found"
        )

    return MetricResult(metric=spec.type, score=score, passed=passed, detail=detail)
