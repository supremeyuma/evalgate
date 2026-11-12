"""Deterministic metric tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from evalgate.metrics import evaluate_metric
from evalgate.metrics.base import MetricContext
from evalgate.models.case import Case
from evalgate.models.suite import (
    ContainsSpec,
    CostSpec,
    ExactMatchSpec,
    JsonSchemaValidSpec,
    LatencySpec,
    Limits,
    LlmJudgeSpec,
    RegexSpec,
)
from evalgate.providers.base import Completion


def _completion(text: str, *, latency_ms: int = 10, cost_usd: str = "0.001") -> Completion:
    return Completion(
        text=text,
        tokens_in=1,
        tokens_out=1,
        cost_usd=Decimal(cost_usd),
        latency_ms=latency_ms,
        model="m",
    )


def _case(**overrides: object) -> Case:
    payload: dict[str, object] = {"id": "a", "input": "hi"}
    payload.update(overrides)
    return Case.model_validate(payload)


def _context(
    *, limits: Limits | None = None, schema: dict[str, object] | None = None
) -> MetricContext:
    documents = {"schema.json": schema} if schema is not None else {}
    return MetricContext(limits=limits or Limits(), schema_documents=documents)


def test_exact_match_pass_and_fail() -> None:
    case = _case(expected="Paris")
    passed = evaluate_metric(ExactMatchSpec(), case, _completion("Paris"), _context())
    failed = evaluate_metric(ExactMatchSpec(), case, _completion("Lyon"), _context())
    assert passed.passed and passed.score == 1.0
    assert not failed.passed and "expected" in (failed.detail or "")


def test_exact_match_normalizes() -> None:
    case = _case(expected="  Paris  ")
    result = evaluate_metric(
        ExactMatchSpec(normalize=True),
        case,
        _completion("  PARIS\n"),
        _context(),
    )
    assert result.passed


def test_exact_match_without_expected_fails() -> None:
    result = evaluate_metric(ExactMatchSpec(), _case(), _completion("x"), _context())
    assert not result.passed
    assert "no expected value" in (result.detail or "")


def test_contains_any_and_all() -> None:
    case = _case()
    text = _completion("The REFUND takes 30 days")
    any_result = evaluate_metric(ContainsSpec(value=["refund", "coupon"]), case, text, _context())
    all_result = evaluate_metric(
        ContainsSpec(value=["refund", "coupon"], mode="all"), case, text, _context()
    )
    assert any_result.passed
    assert not all_result.passed
    assert "coupon" in (all_result.detail or "")


def test_json_schema_valid_with_fences_and_prose() -> None:
    schema: dict[str, object] = {
        "type": "object",
        "required": ["answer"],
        "properties": {"answer": {"type": "string"}},
    }
    spec = JsonSchemaValidSpec(schema_path="schema.json")
    fenced = _completion('Sure!\n```json\n{"answer": "hi"}\n```')
    prose = _completion('Here: {"answer": "hi"} — done')
    assert evaluate_metric(spec, _case(), fenced, _context(schema=schema)).passed
    assert evaluate_metric(spec, _case(), prose, _context(schema=schema)).passed


def test_json_schema_reports_first_error_path() -> None:
    schema: dict[str, object] = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
    }
    result = evaluate_metric(
        JsonSchemaValidSpec(schema_path="schema.json"),
        _case(),
        _completion('{"answer": 5}'),
        _context(schema=schema),
    )
    assert not result.passed
    assert "$.answer" in (result.detail or "")


def test_json_schema_invalid_json_fails() -> None:
    result = evaluate_metric(
        JsonSchemaValidSpec(schema_path="schema.json"),
        _case(),
        _completion("not json at all"),
        _context(schema={"type": "object"}),
    )
    assert not result.passed
    assert "JSON" in (result.detail or "")


def test_json_schema_missing_document_fails() -> None:
    result = evaluate_metric(
        JsonSchemaValidSpec(schema_path="other.json"),
        _case(),
        _completion("{}"),
        _context(schema={"type": "object"}),
    )
    assert not result.passed
    assert "schema was not loaded" in (result.detail or "")


def test_json_schema_rejects_non_object() -> None:
    result = evaluate_metric(
        JsonSchemaValidSpec(schema_path="schema.json"),
        _case(),
        _completion("[1, 2]"),
        _context(schema={"type": "object"}),
    )
    assert not result.passed


def test_regex_metric() -> None:
    spec = RegexSpec(pattern=r"refund \d+ days")
    assert evaluate_metric(spec, _case(), _completion("a refund 30 days"), _context()).passed
    assert not evaluate_metric(spec, _case(), _completion("no timeline"), _context()).passed


def test_latency_metric_with_spec_max() -> None:
    spec = LatencySpec(max=100)
    assert evaluate_metric(spec, _case(), _completion("x", latency_ms=50), _context()).passed
    assert not evaluate_metric(spec, _case(), _completion("x", latency_ms=150), _context()).passed


def test_latency_metric_falls_back_to_limits() -> None:
    spec = LatencySpec()
    assert evaluate_metric(
        spec,
        _case(),
        _completion("x", latency_ms=500),
        _context(limits=Limits(max_p95_latency_ms=1000)),
    ).passed
    assert not evaluate_metric(
        spec,
        _case(),
        _completion("x", latency_ms=1500),
        _context(limits=Limits(max_p95_latency_ms=1000)),
    ).passed


def test_latency_metric_without_limit_passes() -> None:
    result = evaluate_metric(LatencySpec(), _case(), _completion("x"), _context())
    assert result.passed
    assert "no latency limit" in (result.detail or "")


def test_cost_metric_with_spec_max() -> None:
    spec = CostSpec(max=Decimal("0.01"))
    assert evaluate_metric(spec, _case(), _completion("x", cost_usd="0.001"), _context()).passed
    assert not evaluate_metric(spec, _case(), _completion("x", cost_usd="0.02"), _context()).passed


def test_cost_metric_falls_back_to_limits() -> None:
    spec = CostSpec()
    assert evaluate_metric(
        spec,
        _case(),
        _completion("x", cost_usd="0.001"),
        _context(limits=Limits(max_cost_usd=Decimal("0.01"))),
    ).passed


def test_cost_metric_without_limit_passes() -> None:
    result = evaluate_metric(CostSpec(), _case(), _completion("x"), _context())
    assert result.passed
    assert "no cost limit" in (result.detail or "")


def test_registry_rejects_judge_spec() -> None:
    with pytest.raises(ValueError, match="llm_judge"):
        evaluate_metric(LlmJudgeSpec(threshold=4), _case(), _completion("x"), _context())


def test_registry_rejects_unknown_spec() -> None:
    with pytest.raises(ValueError, match="unsupported metric"):
        evaluate_metric(object(), _case(), _completion("x"), _context())
