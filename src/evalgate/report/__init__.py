"""Report artifacts: stable JSON, standalone HTML, and PR comments."""

from __future__ import annotations

from evalgate.report.html_report import render_html, write_html_report
from evalgate.report.json_report import render_json, write_json_report
from evalgate.report.pr_comment import (
    PR_COMMENT_MARKER,
    find_marker_comment,
    post_or_update_comment,
    render_pr_comment,
)

__all__ = [
    "PR_COMMENT_MARKER",
    "find_marker_comment",
    "post_or_update_comment",
    "render_html",
    "render_json",
    "render_pr_comment",
    "write_html_report",
    "write_json_report",
]
