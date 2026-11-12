"""Shared helpers for extracting JSON from model output."""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class JsonExtractionError(ValueError):
    """No parseable JSON value could be found in the text."""


def extract_json(text: str) -> Any:
    """Extract the first parseable JSON value from plain text or a code fence."""

    stripped = text.strip()
    candidates = [stripped]
    fence_match = _FENCE.search(stripped)
    if fence_match is not None:
        candidates.append(fence_match.group(1).strip())

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end > start:
        candidates.append(stripped[start : end + 1])

    last_error: ValueError | None = None
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except ValueError as error:
            last_error = error

    message = "response does not contain parseable JSON"
    if last_error is not None:
        message = f"{message}: {last_error}"
    raise JsonExtractionError(message)


def extract_json_object(text: str) -> dict[str, Any]:
    """Like :func:`extract_json`, but require a JSON object."""

    value = extract_json(text)
    if not isinstance(value, dict):
        message = "response JSON is not an object"
        raise JsonExtractionError(message)
    return value
