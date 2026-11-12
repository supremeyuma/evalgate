"""Render the idempotent pull-request comment."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable

from evalgate.models.result import CaseResult, RunReport

PR_COMMENT_MARKER = "<!-- evalgate:report -->"

RunCommand = Callable[..., subprocess.CompletedProcess[str]]


def find_marker_comment(comments: list[dict[str, object]]) -> dict[str, object] | None:
    for comment in comments:
        body = comment.get("body")
        if isinstance(body, str) and PR_COMMENT_MARKER in body:
            return comment
    return None


def post_or_update_comment(
    *,
    repo: str,
    pr_number: int,
    body: str,
    token: str | None = None,
    run: RunCommand = subprocess.run,
) -> bool:
    """Create or update the marker comment with ``gh api``.

    Returns ``False`` (without raising) when the token is read-only, as on fork PRs.
    """

    env = dict(os.environ)
    if token:
        env["GH_TOKEN"] = token
    try:
        listing = run(
            [
                "gh",
                "api",
                f"repos/{repo}/issues/{pr_number}/comments?per_page=100",
            ],
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )
        comments = json.loads(listing.stdout or "[]")
        existing = find_marker_comment(comments if isinstance(comments, list) else [])
        if existing is not None:
            comment_id = existing.get("id")
            run(
                [
                    "gh",
                    "api",
                    "-X",
                    "PATCH",
                    f"repos/{repo}/issues/comments/{comment_id}",
                    "-f",
                    f"body={body}",
                ],
                capture_output=True,
                text=True,
                check=True,
                env=env,
            )
            return True
        run(
            [
                "gh",
                "api",
                "-X",
                "POST",
                f"repos/{repo}/issues/{pr_number}/comments",
                "-f",
                f"body={body}",
            ],
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )
        return True
    except Exception:
        return False


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _delta(current: float, baseline: float) -> str:
    points = (current - baseline) * 100
    sign = "+" if points >= 0 else ""
    return f"{sign}{points:.1f} pp"


def _verdict(current: float, baseline: float, drop_allowed: float) -> str:
    if current < baseline - drop_allowed:
        return ":x: regression"
    if current > baseline:
        return ":white_check_mark: improved"
    return ":white_check_mark: within threshold"


def _regressed_cases(
    report: RunReport, baseline: RunReport | None, limit: int = 10
) -> list[CaseResult]:
    if baseline is None:
        return [case for case in report.cases if not case.passed][:limit]
    was_passing = {case.case_id: case.passed for case in baseline.cases}
    regressed = [
        case for case in report.cases if not case.passed and was_passing.get(case.case_id, True)
    ]
    return regressed[:limit]


def _case_failure(case: CaseResult) -> str:
    if case.error is not None:
        return f"`run` - {case.error[:140]}"
    failing = [metric for metric in case.metrics if not metric.passed]
    return "; ".join(
        f"`{metric.metric}` - {(metric.detail or 'failed')[:140]}" for metric in failing
    )


def render_pr_comment(
    report: RunReport,
    *,
    baseline: RunReport | None = None,
    artifact_url: str | None = None,
) -> str:
    """Build a stable markdown comment; identical inputs produce identical output."""

    summary = report.summary
    status = ":white_check_mark: passed" if report.exit_code == 0 else ":x: failed"
    lines = [
        PR_COMMENT_MARKER,
        f"## EvalGate - {status}",
        "",
        f"Suite **{report.suite_name}** | `{report.provider}/{report.model_name}` | "
        f"{report.mode} mode | {summary.passed}/{summary.total} cases",
        "",
    ]

    if baseline is not None:
        allowed_drop = (
            report.baseline.regression.max_pass_rate_drop if report.baseline is not None else 0.03
        )
        lines.extend(
            [
                "| Metric | Baseline | Current | Delta | Verdict |",
                "|---|---|---|---|---|",
            ]
        )
        lines.append(
            f"| Pass rate | {_pct(baseline.summary.pass_rate)} | "
            f"{_pct(summary.pass_rate)} | "
            f"{_delta(summary.pass_rate, baseline.summary.pass_rate)} | "
            f"{_verdict(summary.pass_rate, baseline.summary.pass_rate, allowed_drop)} |"
        )
        metric_names = sorted(
            set(summary.metric_pass_rates) | set(baseline.summary.metric_pass_rates)
        )
        for name in metric_names:
            current_rate = summary.metric_pass_rates.get(name, 0.0)
            baseline_rate = baseline.summary.metric_pass_rates.get(name, 0.0)
            lines.append(
                f"| `{name}` | {_pct(baseline_rate)} | {_pct(current_rate)} | "
                f"{_delta(current_rate, baseline_rate)} | "
                f"{_verdict(current_rate, baseline_rate, 0.0)} |"
            )
        lines.append(
            f"| Cost | ${baseline.summary.cost_usd:.4f} | ${summary.cost_usd:.4f} | - | - |"
        )
        lines.append(
            f"| p95 latency | {baseline.summary.p95_latency_ms} ms | "
            f"{summary.p95_latency_ms} ms | - | - |"
        )
        lines.append("")
        if report.baseline is not None:
            regression = report.baseline.regression
            icon = ":x:" if regression.is_regression else ":information_source:"
            lines.append(f"{icon} {regression.reason}")
            lines.append("")
    else:
        lines.extend(
            [
                "| Metric | Value |",
                "|---|---|",
                f"| Pass rate | {_pct(summary.pass_rate)} |",
                f"| Wilson 95% CI | {_pct(summary.wilson_low)} - {_pct(summary.wilson_high)} |",
                f"| Cost | ${summary.cost_usd:.4f} |",
                f"| p95 latency | {summary.p95_latency_ms} ms |",
                "",
                "_No baseline was available; this is the first recorded run._",
                "",
            ]
        )

    for breach in report.limit_breaches:
        lines.append(f"> :x: **Hard limit:** {breach.message}")
        lines.append("")

    if summary.judge_calls + summary.judge_cache_hits:
        total = summary.judge_calls + summary.judge_cache_hits
        lines.append(
            f"Judge cache: {summary.judge_cache_hits}/{total} hits "
            f"({summary.judge_cache_hits / total:.0%}), saved "
            f"${summary.judge_saved_usd:.4f}."
        )
        lines.append("")

    regressed = _regressed_cases(report, baseline)
    if regressed:
        title = "Regressed cases" if baseline is not None else "Failing cases"
        lines.extend(
            [
                f"<details><summary>{title} ({len(regressed)})</summary>",
                "",
                "| Case | Failure |",
                "|---|---|",
            ]
        )
        for case in regressed:
            lines.append(f"| `{case.case_id}` | {_case_failure(case).replace('|', '\\|')} |")
        lines.extend(["", "</details>", ""])

    if artifact_url is not None:
        lines.append(f"[Download the HTML and JSON artifacts]({artifact_url})")
        lines.append("")

    lines.append(
        f"<sub>Run started {report.started_at.isoformat()} | duration {report.duration_ms} ms</sub>"
    )
    return "\n".join(lines) + "\n"
