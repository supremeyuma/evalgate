"""Unit tests for the CLI skeleton."""

from __future__ import annotations

from typer.testing import CliRunner

from evalgate import __version__
from evalgate.cli import app

runner = CliRunner()


def test_help_exits_zero() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "evalgate" in result.stdout.lower()


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_no_args_shows_help() -> None:
    # Click's no_args_is_help exits 2; that is a usage display, not a failure.
    result = runner.invoke(app, [])
    assert result.exit_code == 2
    assert "Usage" in result.stdout
