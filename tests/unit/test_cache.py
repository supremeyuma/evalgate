"""Judge cache key, local backend, and end-to-end cache-hit tests."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from evalgate.constants import JUDGE_MARKER
from evalgate.judges.cache import (
    CacheEntry,
    LocalJudgeCache,
    NullJudgeCache,
    build_judge_cache,
    compute_cache_key,
    compute_rubric_hash,
)
from evalgate.models.case import Case
from evalgate.models.suite import ModelSpec
from evalgate.providers.base import Completion
from evalgate.runner.engine import run_suite


def test_cache_key_is_stable_and_sensitive() -> None:
    base = {
        "response_text": "reply",
        "rubric_hash": compute_rubric_hash("rubric"),
        "judge_model": "judge-a",
    }
    key = compute_cache_key(**base)
    assert key == compute_cache_key(**base)
    assert len(key) == 64
    assert key != compute_cache_key(**{**base, "response_text": "other"})
    assert key != compute_cache_key(**{**base, "rubric_hash": compute_rubric_hash("x")})
    assert key != compute_cache_key(**{**base, "judge_model": "judge-b"})
    assert key != compute_cache_key(**{**base, "prompt_version": "2"})


async def test_local_cache_roundtrip(tmp_path: Path) -> None:
    cache = LocalJudgeCache(tmp_path / "cache.sqlite3")
    entry = CacheEntry(
        hash="a" * 64,
        response_hash="b" * 64,
        rubric_hash="c" * 64,
        model="judge",
        score=4,
        rationale="solid",
        confidence=0.8,
        cost_usd=0.002,
    )
    assert await cache.get(entry.hash) is None
    await cache.put(entry)
    loaded = await cache.get(entry.hash)
    assert loaded is not None
    assert loaded.score == 4
    assert loaded.rationale == "solid"
    assert loaded.cost_usd == pytest.approx(0.002)
    await cache.put(entry)  # idempotent
    await cache.aclose()


async def test_null_cache_never_hits() -> None:
    cache = NullJudgeCache()
    entry = CacheEntry(
        hash="a" * 64,
        response_hash="b" * 64,
        rubric_hash="c" * 64,
        model="judge",
        score=1,
        rationale="x",
        confidence=0.1,
    )
    await cache.put(entry)
    assert await cache.get(entry.hash) is None
    await cache.aclose()


def test_build_cache_selects_backend(tmp_path: Path) -> None:
    local = build_judge_cache(
        backend="local",
        cache_dir=tmp_path,
        database_url="postgresql+asyncpg://x/y",
    )
    assert isinstance(local, LocalJudgeCache)
    null = build_judge_cache(
        backend="local",
        cache_dir=tmp_path,
        database_url="postgresql+asyncpg://x/y",
        no_cache=True,
    )
    assert isinstance(null, NullJudgeCache)
    with pytest.raises(ValueError, match="unknown judge cache backend"):
        build_judge_cache(
            backend="redis", cache_dir=tmp_path, database_url="postgresql+asyncpg://x/y"
        )


class JudgeAwareProvider:
    """Returns 'ok' for generation and strict judge JSON for judge prompts."""

    def __init__(self, judge_reply: dict[str, Any] | None = None) -> None:
        self.generation_calls = 0
        self.judge_calls = 0
        self._judge_reply = judge_reply or {
            "score": 5,
            "rationale": "matches the rubric",
            "confidence": 0.9,
        }

    async def complete(self, *, prompt: str, case: Case, model: ModelSpec) -> Completion:
        if JUDGE_MARKER in prompt:
            self.judge_calls += 1
            text = json.dumps(self._judge_reply)
            cost = Decimal("0.001")
        else:
            self.generation_calls += 1
            text = "ok"
            cost = Decimal("0.0001")
        return Completion(
            text=text,
            tokens_in=1,
            tokens_out=1,
            cost_usd=cost,
            latency_ms=1,
            model=model.name,
        )

    async def aclose(self) -> None:
        return None


def _judge_suite(make_suite: Any, *, rubric: str = "anchors") -> Any:
    return make_suite(
        cases=[{"id": f"c{i}", "input": f"in {i}", "expected": "ok"} for i in range(3)],
        metrics=("  - type: exact_match\n  - type: llm_judge\n    threshold: 4\n"),
        suite_extra="judge:\n  rubric: rubric.md\n",
        extra_files={"rubric.md": rubric},
    )


async def test_second_run_hits_cache(make_suite: Any, tmp_path: Path) -> None:
    loaded = _judge_suite(make_suite)
    provider = JudgeAwareProvider()
    cache = LocalJudgeCache(tmp_path / "judge_cache.sqlite3")

    first = await run_suite(loaded, provider, cache=cache)
    # All three cases share the same response, rubric, and model, so the first judge call
    # is reused within the run. This is content addressing working as intended.
    assert first.summary.judge_calls == 1
    assert first.summary.judge_cache_hits == 2
    assert provider.judge_calls == 1

    second = await run_suite(loaded, provider, cache=cache)
    assert second.summary.judge_calls == 0
    assert second.summary.judge_cache_hits == 3
    assert provider.judge_calls == 1
    assert second.summary.judge_saved_usd == pytest.approx(0.003)
    assert second.summary.pass_rate == 1.0
    await cache.aclose()


async def test_rubric_change_invalidates_cache(make_suite: Any, tmp_path: Path) -> None:
    cache = LocalJudgeCache(tmp_path / "judge_cache.sqlite3")
    provider = JudgeAwareProvider()
    loaded = _judge_suite(make_suite, rubric="first anchors")
    await run_suite(loaded, provider, cache=cache)
    assert provider.judge_calls == 1

    changed = _judge_suite(make_suite, rubric="second anchors")
    report = await run_suite(changed, provider, cache=cache)
    assert provider.judge_calls == 2
    assert report.summary.judge_cache_hits == 2
    await cache.aclose()


async def test_no_cache_never_hits(make_suite: Any) -> None:
    loaded = _judge_suite(make_suite)
    provider = JudgeAwareProvider()
    cache = NullJudgeCache()
    await run_suite(loaded, provider, cache=cache)
    second = await run_suite(loaded, provider, cache=cache)
    assert provider.judge_calls == 6
    assert second.summary.judge_cache_hits == 0
