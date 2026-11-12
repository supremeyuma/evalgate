"""Stable JSON report artifact."""

from __future__ import annotations

from pathlib import Path

from evalgate.models.result import RunReport


def render_json(report: RunReport) -> str:
    """Serialize a report deterministically (field order is model order)."""

    return report.model_dump_json(indent=2) + "\n"


def write_json_report(report: RunReport, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_json(report), encoding="utf-8", newline="\n")
    return destination
