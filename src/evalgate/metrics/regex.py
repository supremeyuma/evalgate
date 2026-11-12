"""Regular-expression metric."""

from __future__ import annotations

import re

from evalgate.metrics.base import clip
from evalgate.models.case import Case
from evalgate.models.result import MetricResult
from evalgate.models.suite import RegexSpec
from evalgate.providers.base import Completion


def evaluate(spec: RegexSpec, case: Case, completion: Completion) -> MetricResult:
    match = re.search(spec.pattern, completion.text)
    passed = match is not None
    detail = (
        f"matched {clip(match.group(0))!r}"
        if passed and match is not None
        else f"pattern {spec.pattern!r} not found"
    )
    return MetricResult(
        metric=spec.type, score=1.0 if passed else 0.0, passed=passed, detail=detail
    )
