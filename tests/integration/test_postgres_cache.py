"""Postgres judge-cache backend against a real container."""

from __future__ import annotations

import pytest

from evalgate.judges.cache import CacheEntry, PostgresJudgeCache

pytestmark = pytest.mark.integration


async def test_postgres_cache_roundtrip() -> None:
    pytest.importorskip("testcontainers.postgres")
    from testcontainers.postgres import PostgresContainer

    try:
        container = PostgresContainer("postgres:16-alpine")
        container.start()
    except Exception as error:  # Docker unavailable
        pytest.skip(f"docker unavailable: {error}")

    try:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(5432)
        url = f"postgresql+asyncpg://test:test@{host}:{port}/test"
        cache = PostgresJudgeCache(url)
        entry = CacheEntry(
            hash="d" * 64,
            response_hash="e" * 64,
            rubric_hash="f" * 64,
            model="judge",
            score=3,
            rationale="adequate",
            confidence=0.6,
            cost_usd=0.001,
        )
        assert await cache.get(entry.hash) is None
        await cache.put(entry)
        loaded = await cache.get(entry.hash)
        assert loaded is not None
        assert loaded.score == 3
        await cache.put(entry)
        await cache.aclose()
    finally:
        container.stop()
