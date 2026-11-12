"""CLI run tests: exit codes, artifacts, and provider configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from evalgate.cli import app

runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parents[2]


def test_run_support_suite_mock(tmp_path: Path) -> None:
    json_out = tmp_path / "report.json"
    html_out = tmp_path / "report.html"
    result = runner.invoke(
        app,
        [
            "run",
            str(REPO_ROOT / "examples" / "support" / "suite.yaml"),
            "--mock",
            "--json",
            str(json_out),
            "--html",
            str(html_out),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "pass rate" in result.stdout.lower()
    assert json_out.is_file()
    assert html_out.is_file()
    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert payload["summary"]["total"] == 40
    assert payload["mode"] == "mock"


def test_run_classification_suite_mock() -> None:
    result = runner.invoke(
        app,
        ["run", str(REPO_ROOT / "examples" / "classification" / "suite.yaml"), "--mock"],
    )
    assert result.exit_code == 0, result.stdout


def test_run_missing_suite_exits_2(tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", str(tmp_path / "nope.yaml"), "--mock"])
    assert result.exit_code == 2
    assert "suite file not found" in result.stderr


def test_run_metric_failure_exits_1(make_suite: Any) -> None:
    loaded = make_suite(metrics="  - type: regex\n    pattern: refund\n")
    result = runner.invoke(app, ["run", str(loaded.path), "--mock"])
    assert result.exit_code == 1
    assert "fail" in result.stdout


def test_run_provider_without_key_exits_2(make_suite: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    loaded = make_suite(provider="openai-compatible", model_name="gpt-4.1-mini")
    result = runner.invoke(app, ["run", str(loaded.path)])
    assert result.exit_code == 2
    assert "OPENAI_API_KEY" in result.stderr


def test_run_baseline_regression_exits_1(make_suite: Any, tmp_path: Path) -> None:
    cases = [{"id": f"c{i:02d}", "input": f"in {i}", "expected": "ok"} for i in range(20)]
    passing = make_suite(cases=cases)
    baseline_path = tmp_path / "baseline.json"
    baseline_result = runner.invoke(
        app,
        ["run", str(passing.path), "--mock", "--json", str(baseline_path)],
    )
    assert baseline_result.exit_code == 0

    failing = make_suite(
        cases=cases,
        metrics="  - type: regex\n    pattern: refund\n",
    )
    report_path = tmp_path / "current.json"
    result = runner.invoke(
        app,
        [
            "run",
            str(failing.path),
            "--mock",
            "--baseline",
            str(baseline_path),
            "--json",
            str(report_path),
        ],
    )
    assert result.exit_code == 1
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["baseline"]["regression"]["is_regression"] is True


def test_run_unreadable_baseline_exits_2(make_suite: Any, tmp_path: Path) -> None:
    loaded = make_suite()
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    result = runner.invoke(app, ["run", str(loaded.path), "--mock", "--baseline", str(bad)])
    assert result.exit_code == 2
    assert "could not read baseline" in result.stderr


def test_run_timeout_option_rejects_zero() -> None:
    result = runner.invoke(
        app,
        [
            "run",
            str(REPO_ROOT / "examples" / "support" / "suite.yaml"),
            "--mock",
            "--timeout",
            "0",
        ],
    )
    assert result.exit_code == 2
