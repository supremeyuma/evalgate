"""Typer command-line interface for EvalGate."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from evalgate import __version__
from evalgate.config import get_settings
from evalgate.models.loader import LoadedSuite, SuiteLoadError, load_suite
from evalgate.models.result import RunReport
from evalgate.models.suite import suite_json_schema
from evalgate.providers import ProviderConfigError, ProviderError, build_provider
from evalgate.report import write_html_report, write_json_report
from evalgate.runner import (
    Baseline,
    RunOptions,
    load_baseline_report,
    run_suite,
)

app = typer.Typer(
    name="evalgate",
    help="Run declarative eval suites against LLM providers and gate pull requests on quality.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()


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


def _print_run_report(report: RunReport) -> None:
    table = Table(
        title=f"{report.suite_name} — {report.provider}/{report.model_name} ({report.mode})",
        header_style="bold",
    )
    table.add_column("Case", overflow="fold")
    table.add_column("Verdict", justify="center")
    table.add_column("Metrics", overflow="fold")
    table.add_column("Latency", justify="right")
    table.add_column("Cost", justify="right")

    for case in report.cases:
        verdict = "[green]pass[/green]" if case.passed else "[red]fail[/red]"
        if case.error is not None:
            metric_text = case.error
        else:
            failing = [metric.metric for metric in case.metrics if not metric.passed]
            metric_text = ", ".join(failing) if failing else "all passed"
        table.add_row(
            case.case_id,
            verdict,
            metric_text,
            f"{case.latency_ms} ms",
            f"${case.cost_usd:.4f}",
        )
    console.print(table)

    summary = report.summary
    summary_text = (
        f"pass rate: [bold]{summary.pass_rate:.1%}[/bold] "
        f"({summary.passed}/{summary.total})\n"
        f"Wilson 95% CI: {summary.wilson_low:.1%} - {summary.wilson_high:.1%}\n"
        f"cost: ${summary.cost_usd:.4f} | p95 latency: {summary.p95_latency_ms} ms | "
        f"errors: {summary.errors}"
    )
    if report.limit_breaches:
        summary_text += "\n" + "\n".join(
            f"[red]{breach.message}[/red]" for breach in report.limit_breaches
        )
    if report.baseline is not None:
        baseline = report.baseline
        color = "red" if baseline.regression.is_regression else "cyan"
        summary_text += (
            f"\n[{color}]baseline {baseline.label}: {baseline.baseline_pass_rate:.1%} → "
            f"{baseline.current_pass_rate:.1%} (delta {baseline.delta:+.1%}); "
            f"{baseline.regression.reason}[/{color}]"
        )
    console.print(Panel(summary_text, title="Summary", expand=False))


async def _execute_run(
    loaded: LoadedSuite,
    *,
    mock: bool,
    options: RunOptions,
    baseline: Baseline | None,
) -> RunReport:
    settings = get_settings()
    provider = build_provider(loaded.suite.model, force_mock=mock, settings=settings)
    try:
        return await run_suite(
            loaded,
            provider,
            judge_model=settings.judge_model,
            options=options,
            baseline=baseline,
        )
    finally:
        await provider.aclose()


@app.command()
def run(
    suite: Annotated[Path, typer.Argument(help="Path to the suite YAML file.")],
    mock: Annotated[
        bool,
        typer.Option("--mock", help="Force the deterministic mock provider (no keys, no network)."),
    ] = False,
    concurrency: Annotated[
        int,
        typer.Option("--concurrency", "-c", min=1, help="Maximum in-flight provider calls."),
    ] = 5,
    json_out: Annotated[
        Path | None,
        typer.Option("--json", help="Write a JSON report to this path."),
    ] = None,
    html_out: Annotated[
        Path | None,
        typer.Option("--html", help="Write a standalone HTML report to this path."),
    ] = None,
    baseline: Annotated[
        Path | None,
        typer.Option("--baseline", help="Baseline JSON report to compare against."),
    ] = None,
    no_cache: Annotated[
        bool,
        typer.Option("--no-cache", help="Bypass judge cache reads and writes."),
    ] = False,
    timeout_s: Annotated[
        float,
        typer.Option("--timeout", min=0.1, help="Per-case timeout in seconds."),
    ] = 60.0,
) -> None:
    """Run a suite; exit 0 on pass, 1 on gate failure, 2 on config error, 3 on infra error."""
    del no_cache  # wired to the judge cache in phase E3
    try:
        loaded = load_suite(suite)
    except SuiteLoadError as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from None

    baseline_value: Baseline | None = None
    if baseline is not None:
        try:
            baseline_value = load_baseline_report(baseline)
        except (OSError, ValueError) as error:
            typer.echo(f"error: could not read baseline {baseline}: {error}", err=True)
            raise typer.Exit(code=2) from None

    options = RunOptions(
        concurrency=concurrency,
        case_timeout_s=timeout_s,
        mode="mock" if mock or loaded.suite.model.provider == "mock" else "live",
    )
    try:
        report = asyncio.run(
            _execute_run(loaded, mock=mock, options=options, baseline=baseline_value)
        )
    except ProviderConfigError as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from None
    except ProviderError as error:
        typer.echo(f"error: provider failure: {error}", err=True)
        raise typer.Exit(code=3) from None

    _print_run_report(report)

    if json_out is not None:
        destination = write_json_report(report, json_out)
        typer.echo(f"wrote {destination}")
    if html_out is not None:
        destination = write_html_report(report, html_out)
        typer.echo(f"wrote {destination}")

    raise typer.Exit(code=report.exit_code)


if __name__ == "__main__":  # pragma: no cover
    app()
