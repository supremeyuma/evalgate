"""Standalone HTML report with inline CSS."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Any

from jinja2 import Environment, select_autoescape

from evalgate.models.result import RunReport

_TEMPLATE_NAME = "report.html.j2"


def render_html(report: RunReport) -> str:
    template_text = (
        files("evalgate.report").joinpath("templates", _TEMPLATE_NAME).read_text(encoding="utf-8")
    )
    environment = Environment(
        autoescape=select_autoescape(enabled_extensions=("html", "j2")),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    environment.filters["pct"] = lambda value: f"{value * 100:.1f}%"
    environment.filters["money"] = lambda value: f"${value:.4f}"
    template = environment.from_string(template_text)
    payload: dict[str, Any] = report.model_dump(mode="json")
    return template.render(
        report=payload,
        failed_cases=[case for case in payload["cases"] if not case["passed"]],
        generated=report.finished_at.strftime("%Y-%m-%d %H:%M UTC"),
    )


def write_html_report(report: RunReport, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_html(report), encoding="utf-8", newline="\n")
    return destination
