"""Deterministic metric registry.

Judges are async and live in :mod:`evalgate.judges`; the runner calls them directly. This
registry covers the metrics that need nothing beyond the case and the completion.
"""

from __future__ import annotations

from evalgate.metrics import contains, cost, exact, json_schema, latency, regex
from evalgate.metrics.base import MetricContext
from evalgate.models.case import Case
from evalgate.models.result import MetricResult
from evalgate.models.suite import (
    ContainsSpec,
    CostSpec,
    ExactMatchSpec,
    JsonSchemaValidSpec,
    LatencySpec,
    LlmJudgeSpec,
    RegexSpec,
)
from evalgate.providers.base import Completion


def evaluate_metric(
    spec: object,
    case: Case,
    completion: Completion,
    context: MetricContext,
) -> MetricResult:
    """Dispatch a metric spec to its implementation."""

    if isinstance(spec, ExactMatchSpec):
        return exact.evaluate(spec, case, completion)
    if isinstance(spec, ContainsSpec):
        return contains.evaluate(spec, case, completion)
    if isinstance(spec, JsonSchemaValidSpec):
        return json_schema.evaluate(spec, case, completion, context.schema_documents)
    if isinstance(spec, RegexSpec):
        return regex.evaluate(spec, case, completion)
    if isinstance(spec, LatencySpec):
        return latency.evaluate(spec, case, completion, context.limits)
    if isinstance(spec, CostSpec):
        return cost.evaluate(spec, case, completion, context.limits)
    if isinstance(spec, LlmJudgeSpec):
        message = "llm_judge metrics are evaluated by the runner with a judge"
        raise ValueError(message)
    message = f"unsupported metric spec: {type(spec).__name__}"
    raise ValueError(message)
