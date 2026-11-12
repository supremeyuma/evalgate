"""LLM-as-judge evaluation with repair, refusal handling, and content-addressed caching."""

from __future__ import annotations

from evalgate.constants import JUDGE_PROMPT_VERSION
from evalgate.judges.cache import (
    CacheEntry,
    JudgeCache,
    NullJudgeCache,
    compute_cache_key,
    compute_response_hash,
    compute_rubric_hash,
)
from evalgate.judges.parser import JudgeParseError, normalize_score, parse_judge_output
from evalgate.judges.rubric import build_judge_prompt
from evalgate.models.case import Case
from evalgate.models.result import MetricResult
from evalgate.models.suite import LlmJudgeSpec, ModelSpec
from evalgate.providers.base import Completion, Provider

_REFUSAL_MARKERS = (
    "i cannot",
    "i can't",
    "i am unable",
    "i'm unable",
    "i won't",
    "i will not",
    "sorry, i can't",
)

_REPAIR_SUFFIX = """

---

Your previous response could not be parsed as the required JSON object:
{error}

Return ONLY the JSON object with keys score, rationale, confidence.
- score is an integer from 1 to 5.
- rationale is one or two sentences.
- confidence is a number between 0 and 1.
No prose, no code fences.
"""


def is_refusal(text: str) -> bool:
    """Detect a judge refusal such as "I cannot evaluate this"."""

    lowered = text.strip().lower()
    return any(marker in lowered[:160] for marker in _REFUSAL_MARKERS)


class Judge:
    """Scores a completion against an anchored rubric with a judge model."""

    def __init__(
        self,
        *,
        provider: Provider,
        base_model: ModelSpec,
        model_name: str,
        rubric_text: str,
        cache: JudgeCache | None = None,
        prompt_version: str = JUDGE_PROMPT_VERSION,
    ) -> None:
        self._provider = provider
        self._model = base_model.model_copy(
            update={"name": model_name, "temperature": 0.0, "max_tokens": 512}
        )
        self._rubric_text = rubric_text
        self._cache: JudgeCache = cache or NullJudgeCache()
        self._prompt_version = prompt_version
        self._rubric_hash = compute_rubric_hash(rubric_text)

    async def _call(self, prompt: str, case: Case) -> Completion:
        return await self._provider.complete(prompt=prompt, case=case, model=self._model)

    async def evaluate(
        self, *, case: Case, completion: Completion, spec: LlmJudgeSpec
    ) -> MetricResult:
        response_hash = compute_response_hash(completion.text)
        cache_key = compute_cache_key(
            response_text=completion.text,
            rubric_hash=self._rubric_hash,
            judge_model=self._model.name,
            prompt_version=self._prompt_version,
        )

        cached = await self._cache.get(cache_key)
        if cached is not None:
            return self._from_cache(cached, spec)

        prompt = build_judge_prompt(
            rubric_text=self._rubric_text, case=case, response=completion.text
        )
        cost_usd = 0.0
        try:
            first = await self._call(prompt, case)
        except Exception as error:
            return self._error(f"provider call failed: {error}")
        cost_usd += float(first.cost_usd)

        if is_refusal(first.text):
            entry = CacheEntry(
                hash=cache_key,
                response_hash=response_hash,
                rubric_hash=self._rubric_hash,
                model=self._model.name,
                score=1,
                rationale=f"judge refused to score: {first.text.strip()[:200]}",
                confidence=0.0,
                cost_usd=cost_usd,
            )
            await self._cache.put(entry)
            return self._verdict(
                score=1,
                rationale=entry.rationale,
                confidence=0.0,
                spec=spec,
                cost_usd=cost_usd,
                repaired=False,
                refusal=True,
            )

        try:
            verdict = parse_judge_output(first.text)
            repaired = False
        except JudgeParseError as first_error:
            repair_prompt = prompt + _REPAIR_SUFFIX.format(error=str(first_error))
            try:
                second = await self._call(repair_prompt, case)
            except Exception as error:
                return self._error(f"repair call failed: {error}")
            cost_usd += float(second.cost_usd)
            try:
                verdict = parse_judge_output(second.text)
                repaired = True
            except JudgeParseError as second_error:
                return self._error(
                    f"invalid judge output after one repair: {second_error} "
                    f"(first error: {first_error})"
                )

        entry = CacheEntry(
            hash=cache_key,
            response_hash=response_hash,
            rubric_hash=self._rubric_hash,
            model=self._model.name,
            score=verdict.score,
            rationale=verdict.rationale,
            confidence=verdict.confidence,
            cost_usd=cost_usd,
        )
        await self._cache.put(entry)
        return self._verdict(
            score=verdict.score,
            rationale=verdict.rationale,
            confidence=verdict.confidence,
            spec=spec,
            cost_usd=cost_usd,
            repaired=repaired,
            refusal=False,
        )

    def _from_cache(self, entry: CacheEntry, spec: LlmJudgeSpec) -> MetricResult:
        passed = entry.score >= spec.threshold
        return MetricResult(
            metric=spec.type,
            score=normalize_score(entry.score),
            passed=passed,
            detail=(
                f"cached score {entry.score}/5 vs threshold {spec.threshold:g}: {entry.rationale}"
            ),
            judge_output={
                "score": entry.score,
                "rationale": entry.rationale,
                "confidence": entry.confidence,
                "model": self._model.name,
                "cached": True,
            },
            cache_hit=True,
            judge_saved_usd=entry.cost_usd,
        )

    def _verdict(
        self,
        *,
        score: int,
        rationale: str,
        confidence: float,
        spec: LlmJudgeSpec,
        cost_usd: float,
        repaired: bool,
        refusal: bool,
    ) -> MetricResult:
        passed = score >= spec.threshold
        detail = f"score {score}/5 vs threshold {spec.threshold:g}: {rationale}"
        return MetricResult(
            metric=spec.type,
            score=normalize_score(score),
            passed=passed,
            detail=detail,
            judge_output={
                "score": score,
                "rationale": rationale,
                "confidence": confidence,
                "model": self._model.name,
                "cached": False,
                "repaired": repaired,
                "refusal": refusal,
            },
            judge_cost_usd=cost_usd,
        )

    @staticmethod
    def _error(message: str) -> MetricResult:
        return MetricResult(
            metric="llm_judge",
            score=0.0,
            passed=False,
            detail=f"judge_error: {message}",
        )
