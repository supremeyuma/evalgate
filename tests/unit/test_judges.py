"""Judge prompt, parser, and evaluation tests."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from evalgate.judges.cache import LocalJudgeCache
from evalgate.judges.judge import Judge
from evalgate.judges.parser import JudgeParseError, normalize_score, parse_judge_output
from evalgate.judges.rubric import build_judge_prompt
from evalgate.models.case import Case
from evalgate.models.suite import LlmJudgeSpec, ModelSpec
from evalgate.providers.base import Completion
from evalgate.providers.mock import MockProvider


def _completion(text: str) -> Completion:
    return Completion(
        text=text,
        tokens_in=1,
        tokens_out=1,
        cost_usd=Decimal(0),
        latency_ms=1,
        model="m",
    )


def test_judge_prompt_contains_all_parts() -> None:
    case = Case(id="a", input="question", context="policy", expected="fact")
    prompt = build_judge_prompt(rubric_text="anchors", case=case, response="candidate")
    assert "EVALGATE_JUDGE_TASK" in prompt
    assert "question" in prompt
    assert "policy" in prompt
    assert "fact" in prompt
    assert "candidate" in prompt
    assert "score" in prompt


def test_parse_judge_output_fenced() -> None:
    verdict = parse_judge_output(
        '```json\n{"score": 4, "rationale": "good", "confidence": 0.8}\n```'
    )
    assert verdict.score == 4


@pytest.mark.parametrize(
    "payload",
    [
        '{"score": 0, "rationale": "x", "confidence": 0.5}',
        '{"score": 6, "rationale": "x", "confidence": 0.5}',
        '{"score": 3, "rationale": "x", "confidence": 2}',
        '{"score": 3, "rationale": "x"}',
        '{"score": "4", "rationale": "x", "confidence": 0.5}',
        "not json",
    ],
)
def test_parse_judge_output_rejects_malformed(payload: str) -> None:
    with pytest.raises(JudgeParseError):
        parse_judge_output(payload)


def test_normalize_score_maps_one_to_five() -> None:
    assert normalize_score(1) == 0.0
    assert normalize_score(3) == 0.5
    assert normalize_score(5) == 1.0


async def test_judge_passes_and_fails_by_threshold(case: Case) -> None:
    judge = Judge(
        provider=MockProvider(),
        base_model=ModelSpec(provider="mock", name="m"),
        model_name="judge",
        rubric_text="anchors",
    )
    result = await judge.evaluate(
        case=case,
        completion=_completion('{"answer": "hi"}'),
        spec=LlmJudgeSpec(threshold=4),
    )
    assert result.passed
    assert result.judge_output is not None
    assert result.judge_output["score"] == 5

    failed = await judge.evaluate(
        case=case,
        completion=_completion("I don't know."),
        spec=LlmJudgeSpec(threshold=4),
    )
    assert not failed.passed
    assert failed.judge_output is not None
    assert failed.judge_output["score"] == 1


class _StaticProvider:
    def __init__(self, text: str) -> None:
        self._text = text

    async def complete(self, *, prompt: str, case: Case, model: ModelSpec) -> Completion:
        return _completion(self._text)

    async def aclose(self) -> None:
        return None


async def test_judge_malformed_output_records_error(case: Case) -> None:
    judge = Judge(
        provider=_StaticProvider("not a verdict"),
        base_model=ModelSpec(provider="mock", name="m"),
        model_name="judge",
        rubric_text="anchors",
    )
    result = await judge.evaluate(
        case=case,
        completion=_completion("anything"),
        spec=LlmJudgeSpec(threshold=4),
    )
    assert not result.passed
    assert "judge_error" in (result.detail or "")


async def test_judge_provider_failure_records_error(case: Case) -> None:
    class _FailingProvider:
        async def complete(self, *, prompt: str, case: Case, model: ModelSpec) -> Completion:
            raise RuntimeError("boom")

        async def aclose(self) -> None:
            return None

    judge = Judge(
        provider=_FailingProvider(),
        base_model=ModelSpec(provider="mock", name="m"),
        model_name="judge",
        rubric_text="anchors",
    )
    result = await judge.evaluate(
        case=case,
        completion=_completion("anything"),
        spec=LlmJudgeSpec(threshold=4),
    )
    assert not result.passed
    assert "provider call failed" in (result.detail or "")


class _SequenceProvider:
    def __init__(self, replies: list[str]) -> None:
        self._replies = replies
        self.calls = 0

    async def complete(self, *, prompt: str, case: Case, model: ModelSpec) -> Completion:
        self.calls += 1
        return _completion(self._replies.pop(0))

    async def aclose(self) -> None:
        return None


async def test_judge_repairs_malformed_output_once(case: Case) -> None:
    provider = _SequenceProvider(["not json", '{"score": 4, "rationale": "ok", "confidence": 0.7}'])
    judge = Judge(
        provider=provider,
        base_model=ModelSpec(provider="mock", name="m"),
        model_name="judge",
        rubric_text="anchors",
    )
    result = await judge.evaluate(
        case=case,
        completion=_completion("reply"),
        spec=LlmJudgeSpec(threshold=4),
    )
    assert result.passed
    assert provider.calls == 2
    assert result.judge_output is not None
    assert result.judge_output["repaired"] is True


async def test_judge_repair_failure_records_error(case: Case) -> None:
    provider = _SequenceProvider(["not json", "still not json"])
    judge = Judge(
        provider=provider,
        base_model=ModelSpec(provider="mock", name="m"),
        model_name="judge",
        rubric_text="anchors",
    )
    result = await judge.evaluate(
        case=case,
        completion=_completion("reply"),
        spec=LlmJudgeSpec(threshold=4),
    )
    assert not result.passed
    assert provider.calls == 2
    assert "after one repair" in (result.detail or "")


async def test_judge_refusal_scores_one_without_repair(case: Case) -> None:
    provider = _SequenceProvider(["I cannot evaluate this response."])
    judge = Judge(
        provider=provider,
        base_model=ModelSpec(provider="mock", name="m"),
        model_name="judge",
        rubric_text="anchors",
    )
    result = await judge.evaluate(
        case=case,
        completion=_completion("reply"),
        spec=LlmJudgeSpec(threshold=4),
    )
    assert not result.passed
    assert provider.calls == 1
    assert result.judge_output is not None
    assert result.judge_output["refusal"] is True
    assert result.judge_output["score"] == 1


async def test_judge_cache_hit_skips_provider(case: Case, tmp_path: Path) -> None:
    provider = _SequenceProvider(['{"score": 5, "rationale": "great", "confidence": 0.9}'])
    cache = LocalJudgeCache(tmp_path / "cache.sqlite3")
    judge = Judge(
        provider=provider,
        base_model=ModelSpec(provider="mock", name="m"),
        model_name="judge",
        rubric_text="anchors",
        cache=cache,
    )
    completion = _completion("reply")
    first = await judge.evaluate(case=case, completion=completion, spec=LlmJudgeSpec(threshold=4))
    second = await judge.evaluate(case=case, completion=completion, spec=LlmJudgeSpec(threshold=4))
    assert provider.calls == 1
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.judge_saved_usd >= 0
    await cache.aclose()
