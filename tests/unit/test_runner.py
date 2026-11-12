"""Runner tests: bounded concurrency, failure isolation, limits, and exit codes."""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from typing import Any

import pytest

from evalgate.models.case import Case
from evalgate.models.result import RunReport
from evalgate.models.suite import ModelSpec
from evalgate.providers.base import Completion, ProviderResponseError
from evalgate.providers.mock import MockProvider
from evalgate.runner.engine import RunOptions, render_prompt, run_suite
from evalgate.runner.regression import Baseline


class ScriptedProvider:
    """Returns per-case text and tracks how many calls are in flight."""

    def __init__(
        self,
        texts: dict[str, str] | None = None,
        *,
        error: Exception | None = None,
        latency_ms: int = 0,
        cost_usd: str = "0",
        delay_s: float = 0.0,
    ) -> None:
        self._texts = texts or {}
        self._error = error
        self._latency_ms = latency_ms
        self._cost = Decimal(cost_usd)
        self._delay = delay_s
        self.in_flight = 0
        self.max_in_flight = 0

    async def complete(self, *, prompt: str, case: Case, model: ModelSpec) -> Completion:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            if self._delay:
                await asyncio.sleep(self._delay)
            if self._error is not None:
                raise self._error
            text = self._texts.get(case.id, "ok")
            return Completion(
                text=text,
                tokens_in=1,
                tokens_out=1,
                cost_usd=self._cost,
                latency_ms=self._latency_ms,
                model=model.name,
            )
        finally:
            self.in_flight -= 1

    async def aclose(self) -> None:
        return None


def _cases(count: int) -> list[dict[str, object]]:
    return [{"id": f"c{i:02d}", "input": f"input {i}", "expected": "ok"} for i in range(count)]


async def test_bounded_concurrency_and_pass(make_suite: Any) -> None:
    loaded = make_suite(cases=_cases(10))
    provider = ScriptedProvider(delay_s=0.01)
    report = await run_suite(loaded, provider, options=RunOptions(concurrency=3))
    assert report.summary.passed == 10
    assert report.summary.pass_rate == 1.0
    assert report.exit_code == 0
    assert provider.max_in_flight <= 3
    assert provider.max_in_flight > 1


async def test_failure_is_isolated(make_suite: Any) -> None:
    loaded = make_suite(cases=_cases(2))
    provider = ScriptedProvider({"c00": "wrong"})
    report = await run_suite(loaded, provider)
    assert report.summary.passed == 1
    assert report.summary.failed == 1
    assert report.exit_code == 1
    failing = [case for case in report.cases if not case.passed]
    assert failing[0].case_id == "c00"
    assert failing[0].metrics[0].metric == "exact_match"


async def test_provider_error_marks_case_and_exits_3(make_suite: Any) -> None:
    loaded = make_suite(cases=_cases(2))
    provider = ScriptedProvider(error=ProviderResponseError("boom"))
    report = await run_suite(loaded, provider)
    assert report.summary.errors == 2
    assert report.exit_code == 3
    assert "provider_error" in (report.cases[0].error or "")


async def test_partial_error_exits_3(make_suite: Any) -> None:
    loaded = make_suite(cases=_cases(1))

    class SometimesFailing:
        def __init__(self) -> None:
            self.calls = 0

        async def complete(self, *, prompt: str, case: Case, model: ModelSpec) -> Completion:
            self.calls += 1
            raise ProviderResponseError("down")

        async def aclose(self) -> None:
            return None

    report = await run_suite(loaded, SometimesFailing())
    assert report.exit_code == 3


async def test_timeout_is_a_case_error(make_suite: Any) -> None:
    loaded = make_suite(cases=_cases(1))
    provider = ScriptedProvider(delay_s=0.05)
    report = await run_suite(loaded, provider, options=RunOptions(case_timeout_s=0.01))
    assert report.exit_code == 3
    assert "timeout" in (report.cases[0].error or "")


async def test_cost_hard_limit_breach(make_suite: Any) -> None:
    loaded = make_suite(
        cases=_cases(2),
        suite_extra="limits:\n  max_cost_usd: 0.001\n",
    )
    provider = ScriptedProvider(cost_usd="0.01")
    report = await run_suite(loaded, provider)
    assert report.exit_code == 1
    assert report.limit_breaches
    assert report.limit_breaches[0].limit == "max_cost_usd"
    assert "hard limit" in report.limit_breaches[0].message


async def test_p95_latency_limit_breach(make_suite: Any) -> None:
    loaded = make_suite(
        cases=_cases(2),
        suite_extra="limits:\n  max_p95_latency_ms: 100\n",
    )
    provider = ScriptedProvider(latency_ms=500)
    report = await run_suite(loaded, provider)
    assert report.exit_code == 1
    assert report.limit_breaches[0].limit == "max_p95_latency_ms"


async def test_no_baseline_failing_case_fails_gate(make_suite: Any) -> None:
    loaded = make_suite(cases=_cases(2))
    report = await run_suite(loaded, ScriptedProvider({"c00": "wrong"}))
    assert report.baseline is None
    assert report.exit_code == 1


async def test_baseline_without_regression_passes_even_with_failures(
    make_suite: Any,
) -> None:
    loaded = make_suite(cases=_cases(2))
    baseline = Baseline(
        label="main",
        suite_name="test-suite",
        pass_rate=0.5,
        wilson_low=0.1,
        wilson_high=0.9,
        total=2,
    )
    report = await run_suite(loaded, ScriptedProvider({"c00": "wrong"}), baseline=baseline)
    assert report.exit_code == 0
    assert report.baseline is not None
    assert not report.baseline.regression.is_regression


async def test_real_regression_on_large_sample(make_suite: Any) -> None:
    loaded = make_suite(cases=_cases(40))
    texts = {f"c{i:02d}": "wrong" for i in range(20)}
    baseline = Baseline(
        label="main",
        suite_name="test-suite",
        pass_rate=1.0,
        wilson_low=0.9121,
        wilson_high=1.0,
        total=40,
    )
    report = await run_suite(loaded, ScriptedProvider(texts), baseline=baseline)
    assert report.summary.pass_rate == 0.5
    assert report.baseline is not None
    assert report.baseline.regression.is_regression
    assert report.exit_code == 1


async def test_template_error_is_isolated(make_suite: Any) -> None:
    loaded = make_suite(cases=_cases(1), prompt="{{ missing_variable }}")
    report = await run_suite(loaded, ScriptedProvider())
    assert report.exit_code == 3
    assert "template_error" in (report.cases[0].error or "")


async def test_llm_judge_integration(make_suite: Any) -> None:
    schema = json.dumps(
        {
            "type": "object",
            "required": ["answer"],
            "properties": {"answer": {"type": "string"}},
        }
    )
    loaded = make_suite(
        cases=[
            {
                "id": "c00",
                "input": "question",
                "expected": "fact",
                "context": "policy",
            }
        ],
        prompt="Return ONLY a JSON object for {{ input }}",
        metrics=(
            "  - type: json_schema_valid\n"
            "    schema: reply.json\n"
            "  - type: llm_judge\n"
            "    threshold: 4\n"
        ),
        suite_extra="judge:\n  rubric: rubric.md\n",
        extra_files={"reply.json": schema, "rubric.md": "1-5 anchors"},
    )
    report = await run_suite(loaded, MockProvider())
    assert report.summary.passed == 1
    assert report.exit_code == 0
    judge_metrics = [metric for metric in report.cases[0].metrics if metric.metric == "llm_judge"]
    assert judge_metrics[0].judge_output is not None


async def test_mode_is_recorded(make_suite: Any) -> None:
    loaded = make_suite(cases=_cases(1))
    report = await run_suite(loaded, ScriptedProvider(), options=RunOptions(mode="mock"))
    assert report.mode == "mock"


async def test_invalid_concurrency_rejected(make_suite: Any) -> None:
    loaded = make_suite(cases=_cases(1))
    with pytest.raises(ValueError, match="concurrency"):
        await run_suite(loaded, ScriptedProvider(), options=RunOptions(concurrency=0))


def test_render_prompt_requires_known_case(make_suite: Any) -> None:
    loaded = make_suite(cases=_cases(1))
    assert "input 0" in render_prompt(loaded, "c00")
    with pytest.raises(StopIteration):
        render_prompt(loaded, "missing")


async def test_report_has_metric_pass_rates(make_suite: Any) -> None:
    loaded = make_suite(cases=_cases(2))
    report: RunReport = await run_suite(loaded, ScriptedProvider())
    assert report.summary.metric_pass_rates == {"exact_match": 1.0}
