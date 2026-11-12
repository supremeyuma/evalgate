"""LLM-as-judge evaluation for one metric and case."""

from __future__ import annotations

from evalgate.judges.parser import JudgeParseError, normalize_score, parse_judge_output
from evalgate.judges.rubric import build_judge_prompt
from evalgate.models.case import Case
from evalgate.models.result import MetricResult
from evalgate.models.suite import LlmJudgeSpec, ModelSpec
from evalgate.providers.base import Completion, Provider


class Judge:
    """Scores a completion against an anchored rubric with a judge model."""

    def __init__(
        self,
        *,
        provider: Provider,
        base_model: ModelSpec,
        model_name: str,
        rubric_text: str,
    ) -> None:
        self._provider = provider
        self._model = base_model.model_copy(
            update={"name": model_name, "temperature": 0.0, "max_tokens": 512}
        )
        self._rubric_text = rubric_text

    async def evaluate(
        self, *, case: Case, completion: Completion, spec: LlmJudgeSpec
    ) -> MetricResult:
        prompt = build_judge_prompt(
            rubric_text=self._rubric_text, case=case, response=completion.text
        )
        try:
            judge_completion = await self._provider.complete(
                prompt=prompt, case=case, model=self._model
            )
        except Exception as error:  # provider failures are case failures, not crashes
            return MetricResult(
                metric=spec.type,
                score=0.0,
                passed=False,
                detail=f"judge_error: provider call failed: {error}",
            )

        try:
            verdict = parse_judge_output(judge_completion.text)
        except JudgeParseError as error:
            return MetricResult(
                metric=spec.type,
                score=0.0,
                passed=False,
                detail=f"judge_error: {error}",
            )

        passed = verdict.score >= spec.threshold
        return MetricResult(
            metric=spec.type,
            score=normalize_score(verdict.score),
            passed=passed,
            detail=(
                f"score {verdict.score}/5 vs threshold {spec.threshold:g}: {verdict.rationale}"
            ),
            judge_output={
                "score": verdict.score,
                "rationale": verdict.rationale,
                "confidence": verdict.confidence,
                "model": self._model.name,
            },
        )
