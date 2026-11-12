"""CLI tests for validate and schema, including the committed contract."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from evalgate import __version__
from evalgate.cli import app

runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parents[2]


def test_help_exits_zero() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "evalgate" in result.stdout.lower()
    assert "validate" in result.stdout
    assert "schema" in result.stdout


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_no_args_shows_help() -> None:
    # Click's no_args_is_help exits 2; that is a usage display, not a failure.
    result = runner.invoke(app, [])
    assert result.exit_code == 2
    assert "Usage" in result.stdout


def test_validate_example_suites() -> None:
    for relative in ["examples/support/suite.yaml", "examples/classification/suite.yaml"]:
        result = runner.invoke(app, ["validate", str(REPO_ROOT / relative)])
        assert result.exit_code == 0, result.stderr
        assert "ok:" in result.stdout


def test_validate_invalid_suite_exits_2(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("name: broken\n", encoding="utf-8")
    result = runner.invoke(app, ["validate", str(path)])
    assert result.exit_code == 2
    assert "error:" in result.stderr


def test_validate_missing_file_exits_2(tmp_path: Path) -> None:
    result = runner.invoke(app, ["validate", str(tmp_path / "missing.yaml")])
    assert result.exit_code == 2
    assert "suite file not found" in result.stderr


def test_schema_matches_committed_document() -> None:
    result = runner.invoke(app, ["schema"])
    assert result.exit_code == 0
    committed = (REPO_ROOT / "docs" / "schema.json").read_text(encoding="utf-8")
    assert result.stdout == committed, (
        "docs/schema.json is stale; run `uv run evalgate schema -o docs/schema.json`"
    )


def test_schema_output_file(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "schema.json"
    result = runner.invoke(app, ["schema", "-o", str(output)])
    assert result.exit_code == 0
    schema = json.loads(output.read_text(encoding="utf-8"))
    assert schema["title"] == "Suite"
    assert "metrics" in schema["properties"]
