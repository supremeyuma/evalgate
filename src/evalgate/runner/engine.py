"""The bounded-concurrency evaluation engine."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from jinja2 import Environment, StrictUndefined, TemplateError

from evalgate.judges.cache import JudgeCache
from evalgate.judges.judge import Judge
from evalgate.metrics import evaluate_metric
from evalgate.metrics.base import MetricContext
from evalgate.models.loader import LoadedSuite
from evalgate.models.result import (
    BaselineComparison,
    CaseResult,
    LimitBreach,
    RunReport,
)
from evalgate.models.suite import LlmJudgeSpec
from evalgate.providers.base import Provider, ProviderError
from evalgate.runner.aggregates import summarize
from evalgate.runner.regression import Baseline, evaluate_regression

_TEMPLATE_ENV = Environment(
    undefined=StrictUndefined,
    autoescape=False,  # noqa: S701 - prompts are plain text, never HTML
)


@dataclass(frozen=True)
class RunOptions:
    """Execution knobs for one run."""

    concurrency: int = 5
    case_timeout_s: float = 60.0
    mode: str = "live"


def render_prompt(loaded: LoadedSuite, case_id: str) -> str:
    """Render the suite prompt for one case."""

    case = next(item for item in loaded.cases if item.id == case_id)
    template = _TEMPLATE_ENV.from_string(loaded.prompt_text)
    return template.render(
        input=case.input,
        context=case.context or "",
        expected=case.expected or "",
        id=case.id,
        tags=case.tags,
    )


def _build_judges(
    loaded: LoadedSuite,
    *,
    provider: Provider,
    judge_model: str,
    cache: JudgeCache | None,
) -> dict[int, Judge]:
    judges: dict[int, Judge] = {}
    for index, spec in enumerate(loaded.suite.metrics):
        if not isinstance(spec, LlmJudgeSpec):
            continue
        rubric = spec.rubric or loaded.suite.judge.rubric
        if rubric is None:  # guarded at validation time
            continue
        judges[index] = Judge(
            provider=provider,
            base_model=loaded.suite.model,
            model_name=loaded.suite.judge.model or judge_model,
            rubric_text=loaded.rubric_texts[rubric],
            cache=cache,
        )
    return judges


async def run_suite(
    loaded: LoadedSuite,
    provider: Provider,
    *,
    judge_provider: Provider | None = None,
    judge_model: str = "gpt-4.1-mini",
    options: RunOptions | None = None,
    baseline: Baseline | None = None,
    cache: JudgeCache | None = None,
) -> RunReport:
    """Run every case with bounded concurrency and return a complete report."""

    run_options = options or RunOptions()
    if run_options.concurrency < 1:
        message = "concurrency must be at least 1"
        raise ValueError(message)
    if run_options.case_timeout_s <= 0:
        message = "case timeout must be positive"
        raise ValueError(message)

    suite = loaded.suite
    context = MetricContext(limits=suite.limits, schema_documents=loaded.schema_documents)
    judges = _build_judges(
        loaded,
        provider=judge_provider or provider,
        judge_model=judge_model,
        cache=cache,
    )
    semaphore = asyncio.Semaphore(run_options.concurrency)
    started_at = datetime.now(UTC)
    started = time.perf_counter()

    async def run_case(case_id: str) -> CaseResult:
        case = next(item for item in loaded.cases if item.id == case_id)
        async with semaphore:
            try:
                prompt = _TEMPLATE_ENV.from_string(loaded.prompt_text).render(
                    input=case.input,
                    context=case.context or "",
                    expected=case.expected or "",
                    id=case.id,
                    tags=case.tags,
                )
            except TemplateError as error:
                return CaseResult(
                    case_id=case.id,
                    passed=False,
                    tags=case.tags,
                    error=f"template_error: {error}",
                )

            try:
                completion = await asyncio.wait_for(
                    provider.complete(prompt=prompt, case=case, model=suite.model),
                    timeout=run_options.case_timeout_s,
                )
            except TimeoutError:
                return CaseResult(
                    case_id=case.id,
                    passed=False,
                    tags=case.tags,
                    error=f"timeout: no completion within {run_options.case_timeout_s:g}s",
                )
            except ProviderError as error:
                return CaseResult(
                    case_id=case.id,
                    passed=False,
                    tags=case.tags,
                    error=f"provider_error: {error}",
                )

            metric_results = []
            for index, spec in enumerate(suite.metrics):
                if isinstance(spec, LlmJudgeSpec):
                    judge = judges.get(index)
                    if judge is None:
                        message = f"no judge configured for metric index {index}"
                        raise ValueError(message)
                    metric_results.append(
                        await judge.evaluate(case=case, completion=completion, spec=spec)
                    )
                else:
                    metric_results.append(evaluate_metric(spec, case, completion, context))

            return CaseResult(
                case_id=case.id,
                passed=all(result.passed for result in metric_results),
                response=completion.text,
                latency_ms=completion.latency_ms,
                cost_usd=float(completion.cost_usd),
                metrics=metric_results,
                tags=case.tags,
            )

    cases = list(await asyncio.gather(*(run_case(case.id) for case in loaded.cases)))
    finished_at = datetime.now(UTC)
    duration_ms = int((time.perf_counter() - started) * 1000)
    summary = summarize(cases)

    breaches: list[LimitBreach] = []
    if (
        suite.limits.max_cost_usd is not None
        and Decimal(str(summary.cost_usd)) > suite.limits.max_cost_usd
    ):
        threshold = float(suite.limits.max_cost_usd)
        breaches.append(
            LimitBreach(
                limit="max_cost_usd",
                threshold=threshold,
                actual=summary.cost_usd,
                message=(
                    f"hard limit: total cost ${summary.cost_usd:.4f} exceeds ${threshold:.4f}"
                ),
            )
        )
    if (
        suite.limits.max_p95_latency_ms is not None
        and summary.p95_latency_ms > suite.limits.max_p95_latency_ms
    ):
        threshold = float(suite.limits.max_p95_latency_ms)
        breaches.append(
            LimitBreach(
                limit="max_p95_latency_ms",
                threshold=threshold,
                actual=float(summary.p95_latency_ms),
                message=(
                    f"hard limit: p95 latency {summary.p95_latency_ms}ms exceeds {threshold:.0f}ms"
                ),
            )
        )

    baseline_comparison: BaselineComparison | None = None
    if baseline is not None:
        regression = evaluate_regression(
            baseline=baseline,
            current_pass_rate=summary.pass_rate,
            current_wilson_low=summary.wilson_low,
            current_wilson_high=summary.wilson_high,
            current_total=summary.total,
            max_pass_rate_drop=suite.regression.max_pass_rate_drop,
            min_cases=suite.regression.min_cases,
        )
        baseline_comparison = BaselineComparison(
            label=baseline.label,
            baseline_pass_rate=baseline.pass_rate,
            current_pass_rate=summary.pass_rate,
            delta=summary.pass_rate - baseline.pass_rate,
            regression=regression,
        )

    # Exit-code policy (documented in docs/eval-suite-spec.md):
    # - any errored case means the run cannot be trusted: infrastructure error (3)
    # - hard-limit breach or a real regression fails the gate (1)
    # - without a baseline, any failing case fails the gate (1); with a baseline the gate
    #   is relative, so cases that also failed in the baseline do not fail the PR
    if summary.errors > 0:
        exit_code = 3
    elif (
        breaches
        or (baseline_comparison is not None and baseline_comparison.regression.is_regression)
        or (baseline_comparison is None and summary.failed > 0)
    ):
        exit_code = 1
    else:
        exit_code = 0

    return RunReport(
        suite_name=suite.name,
        provider=suite.model.provider,
        model_name=suite.model.name,
        mode="mock" if run_options.mode == "mock" else "live",
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        summary=summary,
        cases=cases,
        limit_breaches=breaches,
        baseline=baseline_comparison,
        exit_code=exit_code,
    )
