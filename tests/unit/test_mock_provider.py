"""Deterministic mock and replay provider tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evalgate.constants import JUDGE_MARKER
from evalgate.models.case import Case
from evalgate.models.suite import ModelSpec
from evalgate.providers.base import ProviderResponseError
from evalgate.providers.mock import MockProvider, ReplayProvider

MODEL = ModelSpec(provider="mock", name="m")


async def test_mock_returns_expected_when_prompt_is_plain(case: Case) -> None:
    provider = MockProvider()
    completion = await provider.complete(prompt="Answer: {{ input }}", case=case, model=MODEL)
    assert completion.text == "hello"
    assert completion.cost_usd == 0


async def test_mock_wraps_expected_in_json_for_json_prompt(case: Case) -> None:
    provider = MockProvider()
    completion = await provider.complete(prompt="Return ONLY a JSON object", case=case, model=MODEL)
    payload = json.loads(completion.text)
    assert payload["answer"] == "hello"
    assert payload["citations"] == ["policy"]
    assert payload["confidence"] == 0.9


async def test_mock_is_deterministic(case: Case) -> None:
    provider = MockProvider(simulated_latency_ms=7)
    first = await provider.complete(prompt="p", case=case, model=MODEL)
    second = await provider.complete(prompt="p", case=case, model=MODEL)
    assert first.text == second.text
    assert first.latency_ms == 7


async def test_mock_fixture_map_wins(case: Case) -> None:
    provider = MockProvider({"case-1": "from fixture"})
    completion = await provider.complete(prompt="p", case=case, model=MODEL)
    assert completion.text == "from fixture"


async def test_mock_weakened_marker_returns_bad_answer(case: Case) -> None:
    provider = MockProvider()
    completion = await provider.complete(
        prompt="[[weakened]] Return ONLY a JSON object", case=case, model=MODEL
    )
    assert completion.text == "I don't know."


async def test_mock_judge_prompt_returns_strict_json(case: Case) -> None:
    provider = MockProvider()
    prompt = f"{JUDGE_MARKER}\nCandidate response: " + json.dumps({"answer": "hello"})
    completion = await provider.complete(prompt=prompt, case=case, model=MODEL)
    payload = json.loads(completion.text)
    assert payload["score"] == 5
    assert payload["confidence"] == 0.9
    assert payload["rationale"]


async def test_mock_judge_scores_weak_reply_one(case: Case) -> None:
    provider = MockProvider()
    prompt = f"{JUDGE_MARKER}\nCandidate response: I don't know."
    completion = await provider.complete(prompt=prompt, case=case, model=MODEL)
    assert json.loads(completion.text)["score"] == 1


async def test_replay_reads_fixture(tmp_path: Path, case: Case) -> None:
    fixture = tmp_path / "case-1.json"
    fixture.write_text(
        json.dumps({"text": "replayed", "tokens_in": 3, "tokens_out": 4, "latency_ms": 9}),
        encoding="utf-8",
    )
    provider = ReplayProvider(tmp_path)
    completion = await provider.complete(prompt="p", case=case, model=MODEL)
    assert completion.text == "replayed"
    assert completion.tokens_in == 3
    assert completion.latency_ms == 9


async def test_replay_missing_fixture_raises(tmp_path: Path, case: Case) -> None:
    provider = ReplayProvider(tmp_path)
    with pytest.raises(ProviderResponseError, match="no replay fixture"):
        await provider.complete(prompt="p", case=case, model=MODEL)


async def test_replay_malformed_fixture_raises(tmp_path: Path, case: Case) -> None:
    (tmp_path / "case-1.json").write_text("not json", encoding="utf-8")
    provider = ReplayProvider(tmp_path)
    with pytest.raises(ProviderResponseError, match="invalid replay fixture"):
        await provider.complete(prompt="p", case=case, model=MODEL)


async def test_replay_missing_text_raises(tmp_path: Path, case: Case) -> None:
    (tmp_path / "case-1.json").write_text('{"tokens_in": 1}', encoding="utf-8")
    provider = ReplayProvider(tmp_path)
    with pytest.raises(ProviderResponseError, match="missing text"):
        await provider.complete(prompt="p", case=case, model=MODEL)
