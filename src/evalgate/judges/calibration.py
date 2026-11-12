"""Two-judge calibration: exact agreement, within-one agreement, and Cohen's kappa."""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from evalgate.judges.cache import JudgeCache
from evalgate.judges.judge import Judge
from evalgate.models.loader import LoadedSuite
from evalgate.models.suite import LlmJudgeSpec
from evalgate.providers.base import Provider, ProviderError
from evalgate.runner.engine import render_prompt

CATEGORIES = (1, 2, 3, 4, 5)


class Disagreement(BaseModel):
    """One case where the two judges gave different scores."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    score_a: int
    score_b: int
    rationale_a: str
    rationale_b: str


class CalibrationReport(BaseModel):
    """Observed agreement between two judges on the same responses."""

    model_config = ConfigDict(extra="forbid")

    suite_name: str
    mode: str
    cases_requested: int
    cases_scored: int
    judge_a: str
    judge_b: str
    exact_agreement: float
    within_one_agreement: float
    kappa: float
    errors: int = 0
    disagreements: list[Disagreement] = Field(default_factory=list)


def cohen_kappa(pairs: Sequence[tuple[int, int]], categories: Sequence[int] = CATEGORIES) -> float:
    """Unweighted Cohen's kappa for two raters on ordinal 1-5 scores."""

    if not pairs:
        return 0.0
    total = len(pairs)
    observed = sum(1 for first, second in pairs if first == second) / total
    counts_a = Counter(first for first, _ in pairs)
    counts_b = Counter(second for _, second in pairs)
    expected = sum(counts_a[value] * counts_b[value] for value in categories) / (total * total)
    if expected >= 1.0:
        return 1.0
    return (observed - expected) / (1.0 - expected)


async def run_calibration(
    loaded: LoadedSuite,
    provider: Provider,
    *,
    judge_models: tuple[str, str],
    cache: JudgeCache | None = None,
    max_cases: int = 30,
    mode: str = "live",
    timeout_s: float = 60.0,
) -> CalibrationReport:
    """Score the same generated responses with two judges and measure agreement."""

    judge_spec: LlmJudgeSpec | None = None
    for metric in loaded.suite.metrics:
        if isinstance(metric, LlmJudgeSpec):
            judge_spec = metric
            break
    if judge_spec is None:
        message = "calibration requires a suite with an llm_judge metric"
        raise ValueError(message)

    rubric = judge_spec.rubric or loaded.suite.judge.rubric
    if rubric is None:  # guarded by suite validation
        message = "no rubric configured for llm_judge"
        raise ValueError(message)
    rubric_text = loaded.rubric_texts[rubric]

    judge_a = Judge(
        provider=provider,
        base_model=loaded.suite.model,
        model_name=judge_models[0],
        rubric_text=rubric_text,
        cache=cache,
    )
    judge_b = Judge(
        provider=provider,
        base_model=loaded.suite.model,
        model_name=judge_models[1],
        rubric_text=rubric_text,
        cache=cache,
    )

    selected = loaded.cases[:max_cases]
    pairs: list[tuple[int, int]] = []
    disagreements: list[Disagreement] = []
    errors = 0

    for case in selected:
        prompt = render_prompt(loaded, case.id)
        try:
            completion = await asyncio.wait_for(
                provider.complete(prompt=prompt, case=case, model=loaded.suite.model),
                timeout=timeout_s,
            )
        except (ProviderError, TimeoutError):
            errors += 1
            continue

        result_a = await judge_a.evaluate(case=case, completion=completion, spec=judge_spec)
        result_b = await judge_b.evaluate(case=case, completion=completion, spec=judge_spec)
        output_a = result_a.judge_output
        output_b = result_b.judge_output
        if output_a is None or output_b is None:
            errors += 1
            continue

        score_a = int(output_a["score"])
        score_b = int(output_b["score"])
        pairs.append((score_a, score_b))
        if score_a != score_b:
            disagreements.append(
                Disagreement(
                    case_id=case.id,
                    score_a=score_a,
                    score_b=score_b,
                    rationale_a=str(output_a.get("rationale", "")),
                    rationale_b=str(output_b.get("rationale", "")),
                )
            )

    total = len(pairs)
    exact = sum(1 for first, second in pairs if first == second) / total if total else 0.0
    within_one = (
        sum(1 for first, second in pairs if abs(first - second) <= 1) / total if total else 0.0
    )
    return CalibrationReport(
        suite_name=loaded.suite.name,
        mode=mode,
        cases_requested=min(max_cases, len(loaded.cases)),
        cases_scored=total,
        judge_a=judge_models[0],
        judge_b=judge_models[1],
        exact_agreement=exact,
        within_one_agreement=within_one,
        kappa=cohen_kappa(pairs),
        errors=errors,
        disagreements=disagreements,
    )


def render_calibration_markdown(report: CalibrationReport) -> str:
    label = (
        "mock (deterministic; both judges share the mock provider — this validates the "
        "plumbing, not real judge quality)"
        if report.mode == "mock"
        else "live"
    )
    lines = [
        "# Judge calibration",
        "",
        f"Generated by `evalgate calibrate` on {date.today().isoformat()}.",
        "",
        f"**Provenance:** {label}",
        "",
        f"- Suite: `{report.suite_name}`",
        f"- Judges: `{report.judge_a}` vs `{report.judge_b}`",
        f"- Cases requested: {report.cases_requested}; scored: {report.cases_scored}; "
        f"errors: {report.errors}",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Exact agreement | {report.exact_agreement:.1%} |",
        f"| Within-1 agreement | {report.within_one_agreement:.1%} |",
        f"| Cohen's kappa (unweighted) | {report.kappa:.3f} |",
        "",
        "## Disagreements",
        "",
    ]
    if report.disagreements:
        lines.append("| Case | Judge A | Judge B | Rationale A | Rationale B |")
        lines.append("|---|---|---|---|---|")
        for item in report.disagreements:
            lines.append(
                f"| `{item.case_id}` | {item.score_a} | {item.score_b} | "
                f"{_escape(item.rationale_a)} | {_escape(item.rationale_b)} |"
            )
    else:
        lines.append("No disagreements on the scored cases.")

    lines.extend(
        [
            "",
            "## Method",
            "",
            "- One completion per case is generated once, then scored by both judges.",
            "- Exact agreement is the fraction of cases with identical 1-5 scores.",
            "- Within-1 agreement allows a one-point difference.",
            "- Cohen's kappa is unweighted over the five rubric levels; it corrects for "
            "agreement expected by chance.",
            "- Kappa is unstable on small samples; treat fewer than 30 scored cases as "
            "directional only.",
            "",
            "A live calibration requires provider keys:",
            "",
            "```powershell",
            "uv run evalgate calibrate --suite examples/support/suite.yaml "
            "--judges gpt-4.1-mini,gpt-4.1 --cases 30",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def write_calibration_report(report: CalibrationReport, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_calibration_markdown(report), encoding="utf-8", newline="\n")
    return destination


def _escape(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")
