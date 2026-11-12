"""Parsing and validation of judge JSON output."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from evalgate.metrics.jsonutil import JsonExtractionError, extract_json_object


class JudgeParseError(Exception):
    """The judge response could not be turned into a verdict."""


class JudgeVerdict(BaseModel):
    """The strict JSON contract a judge must satisfy."""

    model_config = ConfigDict(extra="forbid", strict=True)

    score: int = Field(ge=1, le=5)
    rationale: str = Field(min_length=1, max_length=400)
    confidence: float = Field(ge=0.0, le=1.0)


def parse_judge_output(text: str) -> JudgeVerdict:
    """Extract and validate a judge verdict from raw model output."""

    try:
        payload = extract_json_object(text)
    except JsonExtractionError as error:
        raise JudgeParseError(str(error)) from error

    try:
        return JudgeVerdict.model_validate(payload)
    except ValidationError as error:
        details = "; ".join(
            f"{'.'.join(str(part) for part in item['loc']) or '<root>'}: {item['msg']}"
            for item in error.errors()
        )
        raise JudgeParseError(details) from error


def normalize_score(score: int) -> float:
    """Map a 1-5 rubric score onto [0, 1]."""

    return (score - 1) / 4
