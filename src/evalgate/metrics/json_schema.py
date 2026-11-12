"""JSON Schema validity metric."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import jsonschema

from evalgate.metrics.jsonutil import JsonExtractionError, extract_json
from evalgate.models.case import Case
from evalgate.models.result import MetricResult
from evalgate.models.suite import JsonSchemaValidSpec
from evalgate.providers.base import Completion


def _format_path(path: Any) -> str:
    rendered = "$"
    for part in path:
        if isinstance(part, int):
            rendered += f"[{part}]"
        else:
            rendered += f".{part}"
    return rendered


def evaluate(
    spec: JsonSchemaValidSpec,
    case: Case,
    completion: Completion,
    schema_documents: Mapping[str, dict[str, Any]],
) -> MetricResult:
    schema = schema_documents.get(spec.schema_path)
    if schema is None:
        return MetricResult(
            metric=spec.type,
            score=0.0,
            passed=False,
            detail=f"schema was not loaded: {spec.schema_path}",
        )

    try:
        document = extract_json(completion.text)
    except JsonExtractionError as error:
        return MetricResult(metric=spec.type, score=0.0, passed=False, detail=str(error))

    validator = jsonschema.Draft202012Validator(schema)
    first_error: jsonschema.ValidationError | None = next(validator.iter_errors(document), None)
    if first_error is None:
        return MetricResult(metric=spec.type, score=1.0, passed=True, detail="valid JSON")

    detail = f"{_format_path(first_error.absolute_path)}: {first_error.message}"
    return MetricResult(metric=spec.type, score=0.0, passed=False, detail=detail)
