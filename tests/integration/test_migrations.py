"""Alembic migration up/down against a real Postgres database."""

from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from evalgate.storage.db import create_engine
from evalgate.storage.models import Base

REPO_ROOT = Path(__file__).resolve().parents[2]
TABLES = {"suites", "runs", "results", "judge_cache"}


async def _table_names(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
            return {row[0] for row in result}
    finally:
        await engine.dispose()


async def _drop_all(url: str) -> None:
    engine = create_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
    finally:
        await engine.dispose()


def test_alembic_upgrade_and_downgrade(postgres_url: str) -> None:
    asyncio.run(_drop_all(postgres_url))
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", postgres_url.replace("%", "%%"))

    command.upgrade(config, "head")
    assert asyncio.run(_table_names(postgres_url)) >= TABLES

    command.downgrade(config, "base")
    assert not (TABLES & asyncio.run(_table_names(postgres_url)))
