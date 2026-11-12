"""Calibration math and two-judge run tests."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import pytest

from evalgate.constants import JUDGE_MARKER
from evalgate.judges.calibration import (
    cohen_kappa,
    render_calibration_markdown,
    run_calibration,
)
from evalgate.models.case import Case
from evalgate.models.suite import ModelSpec
from evalgate.providers.base import Completion
from evalgate.providers.mock import MockProvider


def test_kappa_perfect_agreement() -> None:
    pairs = [(1, 1), (2, 2), (3, 3), (4, 4), (5, 5)]
    assert cohen_kappa(pairs) == pytest.approx(1.0)


def test_kappa_chance_agreement_is_zero() -> None:
    pairs = [(1, 1), (1, 2), (2, 1), (2, 2)]
    assert cohen_kappa(pairs) == pytest.approx(0.0)


def test_kappa_hand_computed() -> None:
    # observed 3/4, expected 1/2 -> kappa 0.5
    pairs = [(1, 1), (1, 1), (2, 2), (2, 1)]
    assert cohen_kappa(pairs) == pytest.approx(0.5)


def test_kappa_empty() -> None:
    assert cohen_kappa([]) == 0.0


def _calibration_suite(make_suite: Any) -> Any:
    return make_suite(
        cases=[{"id": f"c{i}", "input": f"in {i}", "expected": "ok"} for i in range(5)],
        metrics="  - type: llm_judge\n    threshold: 4\n",
        suite_extra="judge:\n  rubric: rubric.md\n",
        extra_files={"rubric.md": "1-5 anchors"},
    )


async def test_mock_calibration_agrees_with_itself(make_suite: Any) -> None:
    loaded = _calibration_suite(make_suite)
    report = await run_calibration(
        loaded,
        MockProvider(),
        judge_models=("mock-a", "mock-b"),
        max_cases=5,
        mode="mock",
    )
    assert report.cases_scored == 5
    assert report.exact_agreement == 1.0
    assert report.within_one_agreement == 1.0
    assert report.kappa == pytest.approx(1.0)
    assert report.errors == 0


async def test_calibration_requires_judge_metric(make_suite: Any) -> None:
    loaded = make_suite(metrics="  - type: exact_match\n")
    with pytest.raises(ValueError, match="llm_judge"):
        await run_calibration(loaded, MockProvider(), judge_models=("a", "b"), mode="mock")


class BiasedJudgeProvider:
    """Judge model 'a' returns 5, 'b' returns 4; generation returns 'ok'."""

    async def complete(self, *, prompt: str, case: Case, model: ModelSpec) -> Completion:
        if JUDGE_MARKER in prompt:
            score = 5 if model.name == "a" else 4
            text = json.dumps(
                {"score": score, "rationale": f"judge {model.name}", "confidence": 0.8}
            )
        else:
            text = "ok"
        return Completion(
            text=text,
            tokens_in=1,
            tokens_out=1,
            cost_usd=Decimal(0),
            latency_ms=0,
            model=model.name,
        )

    async def aclose(self) -> None:
        return None


async def test_disagreements_are_listed(make_suite: Any) -> None:
    loaded = _calibration_suite(make_suite)
    report = await run_calibration(
        loaded,
        BiasedJudgeProvider(),
        judge_models=("a", "b"),
        max_cases=5,
        mode="mock",
    )
    assert report.cases_scored == 5
    assert report.exact_agreement == 0.0
    assert report.within_one_agreement == 1.0
    assert len(report.disagreements) == 5
    assert report.disagreements[0].score_a == 5
    assert report.disagreements[0].score_b == 4


def test_markdown_labels_mock_provenance() -> None:
    from evalgate.judges.calibration import CalibrationReport

    report = CalibrationReport(
        suite_name="s",
        mode="mock",
        cases_requested=3,
        cases_scored=3,
        judge_a="a",
        judge_b="b",
        exact_agreement=0.7,
        within_one_agreement=1.0,
        kappa=0.4,
    )
    markdown = render_calibration_markdown(report)
    assert "mock (deterministic" in markdown
    assert "70.0%" in markdown
    assert "0.400" in markdown
    assert "Cohen's kappa" in markdown
