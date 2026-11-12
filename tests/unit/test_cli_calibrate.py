"""CLI tests for judge caching and calibration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from evalgate.cli import app

runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parents[2]
SUPPORT_SUITE = REPO_ROOT / "examples" / "support" / "suite.yaml"


def test_second_cli_run_hits_judge_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JUDGE_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("JUDGE_CACHE_BACKEND", "local")
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"

    first = runner.invoke(app, ["run", str(SUPPORT_SUITE), "--mock", "--json", str(first_path)])
    assert first.exit_code == 0, first.stdout
    second = runner.invoke(app, ["run", str(SUPPORT_SUITE), "--mock", "--json", str(second_path)])
    assert second.exit_code == 0, second.stdout

    first_payload = json.loads(first_path.read_text(encoding="utf-8"))
    second_payload = json.loads(second_path.read_text(encoding="utf-8"))
    assert first_payload["summary"]["judge_cache_hits"] == 0
    assert first_payload["summary"]["judge_calls"] == 40
    assert second_payload["summary"]["judge_cache_hits"] == 40
    assert second_payload["summary"]["judge_calls"] == 0


def test_no_cache_flag_bypasses_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JUDGE_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("JUDGE_CACHE_BACKEND", "local")
    report_path = tmp_path / "report.json"
    for _ in range(2):
        result = runner.invoke(
            app,
            ["run", str(SUPPORT_SUITE), "--mock", "--no-cache", "--json", str(report_path)],
        )
        assert result.exit_code == 0
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        assert payload["summary"]["judge_cache_hits"] == 0
        assert payload["summary"]["judge_calls"] == 40


def test_calibrate_mock_writes_report(tmp_path: Path) -> None:
    output = tmp_path / "calibration.md"
    result = runner.invoke(
        app,
        [
            "calibrate",
            str(SUPPORT_SUITE),
            "--mock",
            "--cases",
            "5",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.stdout
    text = output.read_text(encoding="utf-8")
    assert "Judge calibration" in text
    assert "mock (deterministic" in text
    assert "Cohen's kappa" in text
    assert "5" in text


def test_calibrate_rejects_single_judge() -> None:
    result = runner.invoke(app, ["calibrate", str(SUPPORT_SUITE), "--mock", "--judges", "only-one"])
    assert result.exit_code == 2
    assert "exactly two" in result.stderr


def test_calibrate_requires_judge_metric(make_suite: Any) -> None:
    loaded = make_suite(metrics="  - type: exact_match\n")
    result = runner.invoke(app, ["calibrate", str(loaded.path), "--mock"])
    assert result.exit_code == 2
    assert "llm_judge" in result.stderr


def test_calibrate_accepts_suite_option(tmp_path: Path) -> None:
    output = tmp_path / "calibration.md"
    result = runner.invoke(
        app,
        [
            "calibrate",
            "--suite",
            str(SUPPORT_SUITE),
            "--mock",
            "--cases",
            "3",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert output.is_file()


def test_calibrate_defaults_to_support_example(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    output = tmp_path / "calibration.md"
    result = runner.invoke(app, ["calibrate", "--mock", "--cases", "2", "--output", str(output)])
    assert result.exit_code == 0, result.stdout
    assert "support-reply-quality" in output.read_text(encoding="utf-8")
