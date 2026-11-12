"""Strict Pydantic models for the eval-suite YAML contract.

The YAML contract *is* the product: unknown keys are rejected, every path is resolved
relative to the suite file, and invalid combinations fail before a provider is called.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

ProviderName = Literal["openai-compatible", "anthropic", "mock"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ExactMatchSpec(_StrictModel):
    """Compare the response to ``case.expected`` exactly (optionally normalized)."""

    type: Literal["exact_match"] = "exact_match"
    normalize: bool = False


class ContainsSpec(_StrictModel):
    """Require substrings in the response.

    ``mode="any"`` passes if at least one value is present; ``mode="all"`` requires all.
    Matching is case-insensitive.
    """

    type: Literal["contains"] = "contains"
    value: str | list[str]
    mode: Literal["any", "all"] = "any"

    @field_validator("value")
    @classmethod
    def _require_value(cls, value: str | list[str]) -> str | list[str]:
        values = [value] if isinstance(value, str) else value
        if not values or any(not item.strip() for item in values):
            message = "contains.value must be a non-empty string or a non-empty list of strings"
            raise ValueError(message)
        return value


class JsonSchemaValidSpec(_StrictModel):
    """Validate a JSON object parsed from the response against a JSON Schema file."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, populate_by_name=True)

    type: Literal["json_schema_valid"] = "json_schema_valid"
    schema_path: str = Field(alias="schema", serialization_alias="schema", min_length=1)


class RegexSpec(_StrictModel):
    """Require a regular-expression match in the response."""

    type: Literal["regex"] = "regex"
    pattern: str = Field(min_length=1)

    @field_validator("pattern")
    @classmethod
    def _must_compile(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as error:
            message = f"invalid regex pattern: {error}"
            raise ValueError(message) from error
        return value


class LlmJudgeSpec(_StrictModel):
    """Score the response against a rubric with an LLM judge.

    ``threshold`` is the minimum raw rubric score (1-5) required to pass. When ``rubric``
    is omitted, the suite-level ``judge.rubric`` is used.
    """

    type: Literal["llm_judge"] = "llm_judge"
    rubric: str | None = None
    threshold: float = Field(ge=1.0, le=5.0)


class LatencySpec(_StrictModel):
    """Fail when the provider latency exceeds ``max`` milliseconds."""

    type: Literal["latency_ms"] = "latency_ms"
    max: int | None = Field(default=None, gt=0)


class CostSpec(_StrictModel):
    """Fail when the completion cost exceeds ``max`` USD."""

    type: Literal["cost_usd"] = "cost_usd"
    max: Decimal | None = Field(default=None, ge=0)


MetricSpec = Annotated[
    ExactMatchSpec
    | ContainsSpec
    | JsonSchemaValidSpec
    | RegexSpec
    | LlmJudgeSpec
    | LatencySpec
    | CostSpec,
    Field(discriminator="type"),
]


class ModelSpec(_StrictModel):
    """Which provider and model to call for this suite."""

    provider: ProviderName
    name: str = Field(min_length=1)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, gt=0)
    base_url: str | None = None

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith(("http://", "https://")):
            message = "model.base_url must start with http:// or https://"
            raise ValueError(message)
        return value


class Limits(_StrictModel):
    """Hard run limits. A breach fails the run independently of pass rate."""

    max_cost_usd: Decimal | None = Field(default=None, ge=0)
    max_p95_latency_ms: int | None = Field(default=None, gt=0)


class RegressionSpec(_StrictModel):
    """How much pass-rate movement counts as a regression."""

    max_pass_rate_drop: float = Field(default=0.03, ge=0.0, le=1.0)
    min_cases: int = Field(default=10, ge=1)


class JudgeSpec(_StrictModel):
    """Defaults shared by every ``llm_judge`` metric in the suite."""

    model: str | None = None
    rubric: str | None = None


class Suite(_StrictModel):
    """A complete eval suite as authored in YAML."""

    name: str = Field(min_length=1)
    model: ModelSpec
    prompt: str = Field(min_length=1)
    cases_file: str = Field(min_length=1)
    metrics: list[MetricSpec] = Field(min_length=1)
    limits: Limits = Field(default_factory=Limits)
    regression: RegressionSpec = Field(default_factory=RegressionSpec)
    judge: JudgeSpec = Field(default_factory=JudgeSpec)

    @model_validator(mode="after")
    def _require_judge_rubric(self) -> Suite:
        for metric in self.metrics:
            if (
                isinstance(metric, LlmJudgeSpec)
                and metric.rubric is None
                and self.judge.rubric is None
            ):
                message = (
                    "llm_judge metric requires a rubric: set metric.rubric or suite.judge.rubric"
                )
                raise ValueError(message)
        return self


def suite_json_schema() -> dict[str, Any]:
    """Generate the canonical JSON Schema for the suite file contract."""

    return Suite.model_json_schema(mode="validation", by_alias=True)
