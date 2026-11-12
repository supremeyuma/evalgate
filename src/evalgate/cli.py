"""Typer command-line interface for EvalGate."""

from __future__ import annotations

from typing import Annotated

import typer

from evalgate import __version__

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


if __name__ == "__main__":  # pragma: no cover
    app()
