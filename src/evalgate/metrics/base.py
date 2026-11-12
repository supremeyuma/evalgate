"""Metric evaluation context and shared helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from evalgate.models.suite import Limits


@dataclass(frozen=True)
class MetricContext:
    """Suite-level data a metric may need in addition to the case and completion."""

    limits: Limits = field(default_factory=Limits)
    schema_documents: Mapping[str, dict[str, Any]] = field(default_factory=dict)


def clip(text: str, limit: int = 160) -> str:
    """Shorten text for human-readable metric details."""

    single_line = " ".join(text.split())
    if len(single_line) <= limit:
        return single_line
    return single_line[: limit - 1] + "…"
