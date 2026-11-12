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
from evalgate.judges import build_judge_cache
from evalgate.judges.calibration import (
    CalibrationReport,
    run_calibration,
    write_calibration_report,
)
from evalgate.models.loader import LoadedSuite, SuiteLoadError, load_suite
from evalgate.models.result import RunReport
from evalgate.models.suite import suite_json_schema
from evalgate.providers import ProviderConfigError, ProviderError, build_provider
from evalgate.report import (
    post_or_update_comment,
    render_pr_comment,
    write_html_report,
    write_json_report,
)
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
    judge_total = report.summary.judge_calls + report.summary.judge_cache_hits
    if judge_total:
        hit_rate = report.summary.judge_cache_hits / judge_total
        judge_line = (
            f"\njudge: {report.summary.judge_calls} calls | "
            f"{report.summary.judge_cache_hits} cached ({hit_rate:.0%} hit) | "
            f"cost ${report.summary.judge_cost_usd:.4f} | "
            f"saved ${report.summary.judge_saved_usd:.4f}"
        )
    else:
        judge_line = ""

    table = Table(
        title=f"{report.suite_name} - {report.provider}/{report.model_name} ({report.mode})",
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
        f"{judge_line}"
    )
    if report.limit_breaches:
        summary_text += "\n" + "\n".join(
            f"[red]{breach.message}[/red]" for breach in report.limit_breaches
        )
    if report.baseline is not None:
        baseline = report.baseline
        color = "red" if baseline.regression.is_regression else "cyan"
        summary_text += (
            f"\n[{color}]baseline {baseline.label}: {baseline.baseline_pass_rate:.1%} -> "
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
    no_cache: bool,
) -> RunReport:
    settings = get_settings()
    cache = build_judge_cache(
        backend=settings.judge_cache_backend,
        cache_dir=settings.judge_cache_dir,
        database_url=settings.database_url,
        no_cache=no_cache,
    )
    provider = build_provider(loaded.suite.model, force_mock=mock, settings=settings)
    try:
        return await run_suite(
            loaded,
            provider,
            judge_model=settings.judge_model,
            options=options,
            baseline=baseline,
            cache=cache,
        )
    finally:
        await provider.aclose()
        await cache.aclose()


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
            _execute_run(
                loaded,
                mock=mock,
                options=options,
                baseline=baseline_value,
                no_cache=no_cache,
            )
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


async def _execute_calibration(
    loaded: LoadedSuite,
    *,
    mock: bool,
    judge_models: tuple[str, str],
    cases: int,
    timeout_s: float,
) -> CalibrationReport:
    settings = get_settings()
    cache = build_judge_cache(
        backend=settings.judge_cache_backend,
        cache_dir=settings.judge_cache_dir,
        database_url=settings.database_url,
    )
    provider = build_provider(loaded.suite.model, force_mock=mock, settings=settings)
    mode = "mock" if mock or loaded.suite.model.provider == "mock" else "live"
    try:
        return await run_calibration(
            loaded,
            provider,
            judge_models=judge_models,
            cache=cache,
            max_cases=cases,
            mode=mode,
            timeout_s=timeout_s,
        )
    finally:
        await provider.aclose()
        await cache.aclose()


@app.command()
def calibrate(
    suite: Annotated[
        Path | None,
        typer.Argument(help="Path to a suite with an llm_judge metric."),
    ] = None,
    suite_option: Annotated[
        Path | None,
        typer.Option("--suite", help="Path to the suite (alternative to the positional form)."),
    ] = None,
    judges: Annotated[
        str,
        typer.Option(
            "--judges",
            help="Two comma-separated judge model names, e.g. gpt-4.1-mini,gpt-4.1.",
        ),
    ] = "gpt-4.1-mini,gpt-4.1",
    cases: Annotated[
        int,
        typer.Option("--cases", min=1, help="Maximum number of cases to score."),
    ] = 30,
    mock: Annotated[
        bool,
        typer.Option("--mock", help="Use the deterministic mock provider (no keys, no network)."),
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Write a markdown calibration report to this path."),
    ] = None,
    timeout_s: Annotated[
        float,
        typer.Option("--timeout", min=0.1, help="Per-provider-call timeout in seconds."),
    ] = 60.0,
) -> None:
    """Measure agreement between two judges on the same responses."""
    names = [name.strip() for name in judges.split(",") if name.strip()]
    if len(names) != 2:
        typer.echo("error: --judges requires exactly two comma-separated model names", err=True)
        raise typer.Exit(code=2)

    selected_suite = suite or suite_option or Path("examples/support/suite.yaml")
    if not selected_suite.is_file():
        typer.echo(f"error: suite file not found: {selected_suite}", err=True)
        raise typer.Exit(code=2)

    try:
        loaded = load_suite(selected_suite)
    except SuiteLoadError as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from None

    try:
        report = asyncio.run(
            _execute_calibration(
                loaded,
                mock=mock,
                judge_models=(names[0], names[1]),
                cases=cases,
                timeout_s=timeout_s,
            )
        )
    except ProviderConfigError as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from None
    except ValueError as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from None
    except ProviderError as error:
        typer.echo(f"error: provider failure: {error}", err=True)
        raise typer.Exit(code=3) from None

    table = Table(title=f"Judge calibration - {report.suite_name} ({report.mode})")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Cases scored", str(report.cases_scored))
    table.add_row("Errors", str(report.errors))
    table.add_row("Exact agreement", f"{report.exact_agreement:.1%}")
    table.add_row("Within-1 agreement", f"{report.within_one_agreement:.1%}")
    table.add_row("Cohen's kappa", f"{report.kappa:.3f}")
    console.print(table)

    for item in report.disagreements[:10]:
        console.print(
            f"[yellow]{item.case_id}[/yellow]: {item.score_a} vs {item.score_b} - "
            f"{item.rationale_a} / {item.rationale_b}"
        )

    if output is not None:
        destination = write_calibration_report(report, output)
        typer.echo(f"wrote {destination}")
    else:
        typer.echo("pass --output to save the markdown report")


@app.command()
def comment(
    report: Annotated[
        Path,
        typer.Option("--report", exists=True, help="Run JSON report to render."),
    ],
    baseline: Annotated[
        Path | None,
        typer.Option("--baseline", exists=True, help="Optional baseline JSON report."),
    ] = None,
    artifact_url: Annotated[
        str | None,
        typer.Option("--artifact-url", help="Link to uploaded artifacts."),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Write the markdown comment to this file."),
    ] = None,
    repo: Annotated[
        str | None,
        typer.Option("--repo", help="owner/name, required to post the comment."),
    ] = None,
    pr: Annotated[
        int | None,
        typer.Option("--pr", min=1, help="Pull request number."),
    ] = None,
    token: Annotated[
        str | None,
        typer.Option("--token", help="GitHub token; falls back to GH_TOKEN."),
    ] = None,
) -> None:
    """Render the idempotent PR comment, and optionally post it with gh api."""
    try:
        current = RunReport.model_validate_json(report.read_text(encoding="utf-8"))
        baseline_report = (
            RunReport.model_validate_json(baseline.read_text(encoding="utf-8"))
            if baseline is not None
            else None
        )
    except (OSError, ValueError) as error:
        typer.echo(f"error: could not read report: {error}", err=True)
        raise typer.Exit(code=2) from None

    markdown = render_pr_comment(current, baseline=baseline_report, artifact_url=artifact_url)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown, encoding="utf-8", newline="\n")
        typer.echo(f"wrote {output}")
    else:
        typer.echo(markdown, nl=False)

    if repo is None and pr is None:
        return
    if repo is None or pr is None:
        typer.echo("error: --repo and --pr must be provided together", err=True)
        raise typer.Exit(code=2)
    if post_or_update_comment(repo=repo, pr_number=pr, body=markdown, token=token):
        typer.echo(f"posted comment to {repo}#{pr}")
    else:
        typer.echo(
            "notice: could not post the comment (read-only token or missing gh); "
            "the markdown was still rendered",
            err=True,
        )


if __name__ == "__main__":  # pragma: no cover
    app()
