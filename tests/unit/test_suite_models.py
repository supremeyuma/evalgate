"""Tests for the strict suite, case, and metric models."""

from __future__ import annotations

import json

import jsonschema
import pytest
from pydantic import ValidationError

from evalgate.models.case import Case
from evalgate.models.suite import (
    ContainsSpec,
    ExactMatchSpec,
    LlmJudgeSpec,
    RegexSpec,
    Suite,
    suite_json_schema,
)

BASE_SUITE: dict[str, object] = {
    "name": "demo",
    "model": {"provider": "mock", "name": "m"},
    "prompt": "prompt.md",
    "cases_file": "cases.jsonl",
    "metrics": [{"type": "exact_match"}],
}


def _suite(**overrides: object) -> Suite:
    payload = {**BASE_SUITE, **overrides}
    return Suite.model_validate(payload)


def test_minimal_suite_defaults() -> None:
    suite = _suite()
    assert suite.model.temperature == 0.0
    assert suite.model.max_tokens == 1024
    assert suite.regression.max_pass_rate_drop == 0.03
    assert suite.regression.min_cases == 10
    assert suite.limits.max_cost_usd is None
    assert suite.judge.model is None


def test_unknown_top_level_key_rejected() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        _suite(unknown_key=True)


def test_unknown_model_key_rejected() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        _suite(model={"provider": "mock", "name": "m", "temperatur": 0})


def test_bad_provider_rejected() -> None:
    with pytest.raises(ValidationError):
        _suite(model={"provider": "openai", "name": "m"})


def test_base_url_must_be_http() -> None:
    with pytest.raises(ValidationError, match="base_url"):
        _suite(model={"provider": "mock", "name": "m", "base_url": "ftp://example.com"})


def test_temperature_bounds() -> None:
    with pytest.raises(ValidationError):
        _suite(model={"provider": "mock", "name": "m", "temperature": 3})


def test_temperature_zero_allowed() -> None:
    suite = _suite(model={"provider": "mock", "name": "m", "temperature": 0})
    assert suite.model.temperature == 0.0


@pytest.mark.parametrize("threshold", [0.5, 5.5, 0, 6])
def test_judge_threshold_out_of_range(threshold: float) -> None:
    with pytest.raises(ValidationError):
        LlmJudgeSpec(threshold=threshold)


def test_judge_threshold_accepts_bounds() -> None:
    assert LlmJudgeSpec(threshold=1).threshold == 1
    assert LlmJudgeSpec(threshold=5).threshold == 5


def test_llm_judge_requires_rubric_somewhere() -> None:
    with pytest.raises(ValidationError, match="requires a rubric"):
        _suite(metrics=[{"type": "llm_judge", "threshold": 4}])


def test_llm_judge_inherits_suite_rubric() -> None:
    suite = _suite(
        metrics=[{"type": "llm_judge", "threshold": 4}],
        judge={"rubric": "rubrics/helpfulness.md"},
    )
    assert suite.judge.rubric == "rubrics/helpfulness.md"


def test_json_schema_metric_uses_schema_alias() -> None:
    suite = _suite(metrics=[{"type": "json_schema_valid", "schema": "schemas/reply.json"}])
    dumped = suite.metrics[0].model_dump(by_alias=True)
    assert dumped == {"type": "json_schema_valid", "schema": "schemas/reply.json"}


def test_json_schema_metric_rejects_unknown_key() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        _suite(metrics=[{"type": "json_schema_valid", "schema": "s.json", "extra": 1}])


def test_invalid_regex_rejected() -> None:
    with pytest.raises(ValidationError, match="invalid regex"):
        RegexSpec(pattern="[unclosed")


def test_contains_requires_values() -> None:
    with pytest.raises(ValidationError):
        ContainsSpec(value="")
    with pytest.raises(ValidationError):
        ContainsSpec(value=[])
    with pytest.raises(ValidationError):
        ContainsSpec(value=["ok", "  "])


def test_contains_mode_and_list() -> None:
    spec = ContainsSpec(value=["refund", "days"], mode="all")
    assert spec.mode == "all"


def test_exact_match_defaults_to_exact() -> None:
    assert ExactMatchSpec().normalize is False


def test_empty_metrics_rejected() -> None:
    with pytest.raises(ValidationError):
        _suite(metrics=[])


def test_regression_bounds() -> None:
    with pytest.raises(ValidationError):
        _suite(regression={"max_pass_rate_drop": 1.5})
    with pytest.raises(ValidationError):
        _suite(regression={"min_cases": 0})


def test_case_id_whitespace_rejected() -> None:
    with pytest.raises(ValidationError, match="whitespace"):
        Case(id="bad id", input="hello")


def test_case_tags_deduplicated() -> None:
    case = Case(id="a", input="hi", tags=["x", "x", "y"])
    assert case.tags == ["x", "y"]


def test_case_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        Case.model_validate({"id": "a", "input": "hi", "inputt": "typo"})


def test_generated_schema_is_valid_json_schema() -> None:
    schema = suite_json_schema()
    jsonschema.validators.validator_for(schema).check_schema(schema)


def test_generated_schema_documents_metric_types() -> None:
    schema = suite_json_schema()
    metric_refs = json.dumps(schema["$defs"])
    for metric_type in [
        "exact_match",
        "contains",
        "json_schema_valid",
        "regex",
        "llm_judge",
        "latency_ms",
        "cost_usd",
    ]:
        assert metric_type in metric_refs
