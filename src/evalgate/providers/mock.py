"""Deterministic providers for offline demos, tests, and CI.

``MockProvider`` manufactures plausible output from the case itself; ``ReplayProvider``
replays recorded completions from disk. Neither touches the network.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

from evalgate.constants import JUDGE_MARKER
from evalgate.models.case import Case
from evalgate.models.suite import ModelSpec
from evalgate.providers.base import Completion, ProviderResponseError

_WEAKENED_MARKER = "[[weakened]]"
_JUDGE_SCORE_FIVE = "5"
_JUDGE_SCORE_ONE = "1"


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class MockProvider:
    """Deterministic completions.

    - Judge prompts return a strict judge JSON object scored from the candidate response.
    - Prompts containing ``[[weakened]]`` return a deliberately unhelpful answer, which the
      demo uses to show the gate catching a regression.
    - Otherwise the case's ``expected`` value is returned, wrapped in the reply schema when
      the prompt asks for JSON.
    """

    def __init__(
        self,
        fixtures: Mapping[str, str] | None = None,
        *,
        simulated_latency_ms: int = 0,
    ) -> None:
        self._fixtures = dict(fixtures or {})
        self._latency_ms = max(0, simulated_latency_ms)

    async def complete(self, *, prompt: str, case: Case, model: ModelSpec) -> Completion:
        if JUDGE_MARKER in prompt:
            text = self._judge_reply(prompt)
        elif _WEAKENED_MARKER in prompt:
            text = "I don't know."
        elif case.id in self._fixtures:
            text = self._fixtures[case.id]
        elif "Return ONLY a JSON object" in prompt and case.expected is not None:
            citation = (case.context or "policy context").split(".")[0].strip()
            text = json.dumps(
                {
                    "answer": case.expected,
                    "citations": [citation or "policy context"],
                    "confidence": 0.9,
                }
            )
        elif case.expected is not None:
            text = case.expected
        else:
            text = f"mock completion for {case.id}"

        return Completion(
            text=text,
            tokens_in=_estimate_tokens(prompt),
            tokens_out=_estimate_tokens(text),
            cost_usd=Decimal(0),
            latency_ms=self._latency_ms,
            model=model.name,
            raw=None,
        )

    @staticmethod
    def _judge_reply(prompt: str) -> str:
        score = _JUDGE_SCORE_FIVE if '"answer"' in prompt else _JUDGE_SCORE_ONE
        if "I don't know." in prompt and '"answer"' not in prompt:
            score = _JUDGE_SCORE_ONE
        return json.dumps(
            {
                "score": int(score),
                "rationale": "Mock judge: deterministic score derived from the reply shape.",
                "confidence": 0.9,
            }
        )

    async def aclose(self) -> None:
        return None


class ReplayProvider:
    """Replay completions from ``<directory>/<case id>.json`` files."""

    def __init__(self, directory: str | Path) -> None:
        self._directory = Path(directory)

    async def complete(self, *, prompt: str, case: Case, model: ModelSpec) -> Completion:
        path = self._directory / f"{case.id}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            message = f"no replay fixture for case {case.id!r}: {path}"
            raise ProviderResponseError(message) from error
        except json.JSONDecodeError as error:
            message = f"invalid replay fixture {path}: {error.msg}"
            raise ProviderResponseError(message) from error
        if not isinstance(payload, dict):
            raise ProviderResponseError(f"replay fixture must be an object: {path}")

        text = payload.get("text")
        if not isinstance(text, str):
            raise ProviderResponseError(f"replay fixture is missing text: {path}")
        latency_ms = payload.get("latency_ms", 0)
        tokens_in = payload.get("tokens_in", 0)
        tokens_out = payload.get("tokens_out", 0)
        if not all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in (latency_ms, tokens_in, tokens_out)
        ):
            raise ProviderResponseError(f"replay fixture has invalid counts: {path}")

        return Completion(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=Decimal(0),
            latency_ms=latency_ms,
            model=str(payload.get("model") or model.name),
            raw=payload,
        )

    async def aclose(self) -> None:
        return None
