"""Typer command-line interface for EvalGate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from evalgate import __version__
from evalgate.models.loader import SuiteLoadError, load_suite
from evalgate.models.suite import suite_json_schema

app = typer.Typer(
    name="evalgate",
    help="Run declarative eval suites against LLM providers and gate pull requests on quality.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"evalgate {__version__}")
        raise typer.Exit


def _render_schema() -> str:
    return json.dumps(suite_json_schema(), indent=2, sort_keys=True) + "\n"


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show the EvalGate version and exit.",
            callback=_print_version,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """EvalGate: eval suites, judges, and CI regression gates for LLM features."""


@app.command()
def validate(
    suite: Annotated[Path, typer.Argument(help="Path to the suite YAML file.")],
) -> None:
    """Validate a suite file, its dataset, and every referenced asset (exit 2 on error)."""
    try:
        loaded = load_suite(suite)
    except SuiteLoadError as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from None

    spec = loaded.suite
    metric_names = ", ".join(metric.type for metric in spec.metrics)
    typer.echo(f"ok: {spec.name}")
    typer.echo(f"  suite: {loaded.path}")
    typer.echo(f"  model: {spec.model.provider}/{spec.model.name}")
    typer.echo(f"  cases: {len(loaded.cases)}")
    typer.echo(f"  metrics: {metric_names}")


@app.command()
def schema(
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Write the schema to this file instead of stdout."),
    ] = None,
) -> None:
    """Emit the JSON Schema for the eval-suite YAML contract."""
    document = _render_schema()
    if output is None:
        typer.echo(document, nl=False)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8", newline="\n")
    typer.echo(f"wrote {output}")


if __name__ == "__main__":  # pragma: no cover
    app()
