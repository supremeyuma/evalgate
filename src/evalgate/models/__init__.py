"""Strict Pydantic models for suites, cases, and run results."""

from __future__ import annotations

from evalgate.models.case import Case
from evalgate.models.loader import LoadedSuite, SuiteLoadError, load_suite
from evalgate.models.suite import (
    ContainsSpec,
    CostSpec,
    ExactMatchSpec,
    JsonSchemaValidSpec,
    JudgeSpec,
    LatencySpec,
    Limits,
    LlmJudgeSpec,
    ModelSpec,
    RegexSpec,
    RegressionSpec,
    Suite,
    suite_json_schema,
)

__all__ = [
    "Case",
    "ContainsSpec",
    "CostSpec",
    "ExactMatchSpec",
    "JsonSchemaValidSpec",
    "JudgeSpec",
    "LatencySpec",
    "Limits",
    "LlmJudgeSpec",
    "LoadedSuite",
    "ModelSpec",
    "RegexSpec",
    "RegressionSpec",
    "Suite",
    "SuiteLoadError",
    "load_suite",
    "suite_json_schema",
]
