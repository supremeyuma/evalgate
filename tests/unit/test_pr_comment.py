"""PR comment rendering, idempotency marker, and gh posting behavior."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from evalgate.cli import app
from evalgate.models.result import (
    BaselineComparison,
    CaseResult,
    LimitBreach,
    MetricResult,
    RegressionResult,
    RunReport,
    RunSummary,
)
from evalgate.report.pr_comment import (
    PR_COMMENT_MARKER,
    find_marker_comment,
    post_or_update_comment,
    render_pr_comment,
)
from evalgate.runner.aggregates import summarize

runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parents[2]


def _metric(name: str, passed: bool, detail: str = "detail") -> MetricResult:
    return MetricResult(metric=name, score=1.0 if passed else 0.0, passed=passed, detail=detail)


def _case(case_id: str, passed: bool, detail: str = "failed") -> CaseResult:
    return CaseResult(
        case_id=case_id,
        passed=passed,
        metrics=[_metric("exact_match", passed, detail)],
    )


def _report(
    cases: list[CaseResult],
    *,
    exit_code: int = 0,
    limit_breaches: list[LimitBreach] | None = None,
    baseline: BaselineComparison | None = None,
) -> RunReport:
    summary: RunSummary = summarize(cases)
    now = datetime.now(UTC)
    return RunReport(
        suite_name="demo-suite",
        provider="mock",
        model_name="mock",
        mode="mock",
        started_at=now,
        finished_at=now,
        duration_ms=12,
        summary=summary,
        cases=cases,
        limit_breaches=limit_breaches or [],
        baseline=baseline,
        exit_code=exit_code,
    )


def test_marker_is_present_once_and_output_is_ascii() -> None:
    markdown = render_pr_comment(_report([_case("a", True)]))
    assert markdown.count(PR_COMMENT_MARKER) == 1
    assert markdown.isascii()
    assert ":white_check_mark: passed" in markdown


def test_no_baseline_lists_failing_cases() -> None:
    report = _report([_case("ok", True), _case("bad", False, "expected 'refund'")], exit_code=1)
    markdown = render_pr_comment(report)
    assert ":x: failed" in markdown
    assert "No baseline was available" in markdown
    assert "`bad`" in markdown
    assert "expected 'refund'" in markdown


def test_baseline_table_and_regression_reason() -> None:
    baseline = _report([_case("a", True), _case("b", True)])
    current_cases = [_case("a", True), _case("b", False, "broke")]
    regression = RegressionResult(
        is_regression=True,
        reason="pass rate fell 0.500 and intervals do not overlap",
        baseline_pass_rate=1.0,
        current_pass_rate=0.5,
        drop=0.5,
        max_pass_rate_drop=0.03,
        intervals_overlap=False,
        sample_size_ok=True,
    )
    comparison = BaselineComparison(
        label="main",
        baseline_pass_rate=1.0,
        current_pass_rate=0.5,
        delta=-0.5,
        regression=regression,
    )
    markdown = render_pr_comment(
        _report(current_cases, exit_code=1, baseline=comparison), baseline=baseline
    )
    assert "| Pass rate | 100.0% | 50.0% | -50.0 pp |" in markdown
    assert ":x: regression" in markdown
    assert "intervals do not overlap" in markdown
    assert "Regressed cases" in markdown


def test_regressed_cases_exclude_already_failing() -> None:
    baseline = _report([_case("was-failing", False), _case("was-passing", True)])
    current = _report([_case("was-failing", False), _case("was-passing", False)], exit_code=1)
    markdown = render_pr_comment(current, baseline=baseline)
    assert "`was-passing`" in markdown
    assert "`was-failing`" not in markdown


def test_hard_limit_banner() -> None:
    breach = LimitBreach(
        limit="max_cost_usd",
        threshold=0.01,
        actual=0.02,
        message="hard limit: total cost $0.0200 exceeds $0.0100",
    )
    markdown = render_pr_comment(_report([_case("a", True)], exit_code=1, limit_breaches=[breach]))
    assert "Hard limit" in markdown
    assert "exceeds" in markdown


def test_find_marker_comment() -> None:
    comments: list[dict[str, Any]] = [
        {"id": 1, "body": "unrelated"},
        {"id": 2, "body": f"{PR_COMMENT_MARKER}\nhello"},
    ]
    found = find_marker_comment(comments)
    assert found is not None
    assert found["id"] == 2
    assert find_marker_comment([{"id": 1, "body": "x"}]) is None


class _FakeRun:
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        output = self._responses.pop(0)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=output, stderr="")


def test_post_creates_when_marker_absent() -> None:
    fake = _FakeRun(["[]", "{}"])
    assert post_or_update_comment(repo="o/r", pr_number=7, body="body", token="t", run=fake)
    assert any("POST" in call for call in fake.calls)


def test_post_updates_existing_marker() -> None:
    listing = json.dumps([{"id": 42, "body": f"{PR_COMMENT_MARKER}\nold"}])
    fake = _FakeRun([listing, "{}"])
    assert post_or_update_comment(repo="o/r", pr_number=7, body="body", token="t", run=fake)
    patch_call = fake.calls[-1]
    assert "PATCH" in patch_call
    assert any("comments/42" in part for part in patch_call)


def test_post_returns_false_on_read_only_token() -> None:
    def failing(args: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(1, args, stderr="403")

    assert not post_or_update_comment(repo="o/r", pr_number=7, body="body", token="t", run=failing)


def test_comment_cli_writes_markdown(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    run_result = runner.invoke(
        app,
        [
            "run",
            str(REPO_ROOT / "examples" / "consumer" / "suite.yaml"),
            "--mock",
            "--json",
            str(report_path),
        ],
    )
    assert run_result.exit_code == 0
    output = tmp_path / "comment.md"
    result = runner.invoke(app, ["comment", "--report", str(report_path), "--output", str(output)])
    assert result.exit_code == 0
    assert PR_COMMENT_MARKER in output.read_text(encoding="utf-8")


def test_comment_cli_rejects_bad_report(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    result = runner.invoke(app, ["comment", "--report", str(bad)])
    assert result.exit_code == 2


def test_comment_cli_requires_repo_and_pr_together(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    runner.invoke(
        app,
        [
            "run",
            str(REPO_ROOT / "examples" / "consumer" / "suite.yaml"),
            "--mock",
            "--json",
            str(report_path),
        ],
    )
    result = runner.invoke(app, ["comment", "--report", str(report_path), "--repo", "o/r"])
    assert result.exit_code == 2


def test_action_yaml_is_composite() -> None:
    document = yaml.safe_load((REPO_ROOT / "action.yml").read_text(encoding="utf-8"))
    assert document["runs"]["using"] == "composite"
    assert document["inputs"]["suite"]["required"] is True
    assert document["outputs"]["pass-rate"]["value"]
    steps = document["runs"]["steps"]
    assert any(step.get("id") == "run" for step in steps)


def test_consumer_workflow_references_local_action() -> None:
    document = yaml.safe_load(
        (REPO_ROOT / "examples" / "consumer" / ".github" / "workflows" / "evalgate.yml").read_text(
            encoding="utf-8"
        )
    )
    uses = [step.get("uses") for step in document["jobs"]["evalgate"]["steps"] if "uses" in step]
    assert "./" in uses


@pytest.mark.parametrize("path", ["action.yml", "examples/consumer/suite.yaml"])
def test_yaml_files_parse(path: str) -> None:
    assert yaml.safe_load((REPO_ROOT / path).read_text(encoding="utf-8")) is not None
