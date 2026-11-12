"""Integration fixtures: real Postgres and Redis (CI services or Testcontainers)."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from evalgate.config import Settings
from evalgate.storage.db import create_engine, create_session_factory
from evalgate.storage.models import Base
from evalgate.storage.repository import RunRepository


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    env_url = os.environ.get("EVALGATE_TEST_DATABASE_URL")
    if env_url:
        yield env_url
        return

    from testcontainers.community.postgres import PostgresContainer

    try:
        container = PostgresContainer("postgres:16-alpine")
        container.start()
    except Exception as error:
        pytest.skip(f"docker unavailable: {error}")

    try:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(5432)
        yield f"postgresql+asyncpg://test:test@{host}:{port}/test"
    finally:
        container.stop()


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    env_url = os.environ.get("EVALGATE_TEST_REDIS_URL")
    if env_url:
        yield env_url
        return

    from testcontainers.community.redis import RedisContainer

    try:
        container = RedisContainer("redis:7-alpine")
        container.start()
    except Exception as error:
        pytest.skip(f"docker unavailable: {error}")

    try:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"
    finally:
        container.stop()


async def _reset_schema(url: str) -> None:
    engine = create_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


@pytest.fixture
def database(postgres_url: str) -> str:
    asyncio.run(_reset_schema(postgres_url))
    return postgres_url


@pytest.fixture
async def session_factory(
    database: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_engine(database)
    factory = create_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture
def repository(
    session_factory: async_sessionmaker[AsyncSession],
) -> RunRepository:
    return RunRepository(session_factory)


@pytest.fixture
def api_settings(database: str) -> Settings:
    return Settings(
        _env_file=None,
        database_url=database,
        evalgate_api_key="test-key",
        judge_cache_backend="postgres",
        judge_cache_dir=Path(".evalgate-cache"),
    )


@pytest.fixture
async def redis_client(redis_url: str) -> AsyncIterator[Any]:
    import redis.asyncio as redis

    client = redis.Redis.from_url(redis_url)
    try:
        yield client
    finally:
        await client.aclose()
