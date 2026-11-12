"""Report artifacts: stable JSON and a self-contained HTML page."""

from __future__ import annotations

from evalgate.report.html_report import render_html, write_html_report
from evalgate.report.json_report import render_json, write_json_report

__all__ = [
    "render_html",
    "render_json",
    "write_html_report",
    "write_json_report",
]
