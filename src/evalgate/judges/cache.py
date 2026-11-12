"""Content-addressed judge cache.

Key = ``sha256(response_text || rubric_hash || judge_model || prompt_version)``.
The cache stores the rubric score, not the pass/fail verdict, so changing a threshold does
not invalidate cached judgments. Changing the rubric, model, response, or judge prompt
version does.
"""

from __future__ import annotations

import asyncio
import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from evalgate.constants import JUDGE_PROMPT_VERSION
from evalgate.storage.models import Base, JudgeCacheRow

_SEPARATOR = "\x1f"


class CacheEntry(BaseModel):
    """A cached rubric verdict."""

    model_config = ConfigDict(extra="forbid")

    hash: str
    response_hash: str
    rubric_hash: str
    model: str
    score: int = Field(ge=1, le=5)
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)
    cost_usd: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class JudgeCache(Protocol):
    """Storage backend for judge verdicts."""

    async def get(self, key: str) -> CacheEntry | None: ...

    async def put(self, entry: CacheEntry) -> None: ...

    async def aclose(self) -> None: ...


def compute_rubric_hash(rubric_text: str) -> str:
    return hashlib.sha256(rubric_text.encode("utf-8")).hexdigest()


def compute_response_hash(response_text: str) -> str:
    return hashlib.sha256(response_text.encode("utf-8")).hexdigest()


def compute_cache_key(
    *,
    response_text: str,
    rubric_hash: str,
    judge_model: str,
    prompt_version: str = JUDGE_PROMPT_VERSION,
) -> str:
    payload = _SEPARATOR.join([response_text, rubric_hash, judge_model, prompt_version])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class NullJudgeCache:
    """A cache that never reads or writes (``--no-cache``)."""

    async def get(self, key: str) -> CacheEntry | None:
        return None

    async def put(self, entry: CacheEntry) -> None:
        return None

    async def aclose(self) -> None:
        return None


class LocalJudgeCache:
    """SQLite cache for keyless CLI use (``.evalgate-cache/judge_cache.sqlite3``)."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self._path, check_same_thread=False)
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS judge_cache (
                hash TEXT PRIMARY KEY,
                response_hash TEXT NOT NULL,
                rubric_hash TEXT NOT NULL,
                model TEXT NOT NULL,
                score INTEGER NOT NULL,
                rationale TEXT NOT NULL,
                confidence REAL NOT NULL,
                cost_usd REAL NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    async def get(self, key: str) -> CacheEntry | None:
        row = self._connection.execute(
            """
            SELECT hash, response_hash, rubric_hash, model, score, rationale,
                   confidence, cost_usd, created_at
            FROM judge_cache WHERE hash = ?
            """,
            (key,),
        ).fetchone()
        if row is None:
            return None
        return CacheEntry(
            hash=str(row[0]),
            response_hash=str(row[1]),
            rubric_hash=str(row[2]),
            model=str(row[3]),
            score=int(row[4]),
            rationale=str(row[5]),
            confidence=float(row[6]),
            cost_usd=float(row[7]),
            created_at=datetime.fromisoformat(str(row[8])),
        )

    async def put(self, entry: CacheEntry) -> None:
        self._connection.execute(
            """
            INSERT OR IGNORE INTO judge_cache
                (hash, response_hash, rubric_hash, model, score, rationale,
                 confidence, cost_usd, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.hash,
                entry.response_hash,
                entry.rubric_hash,
                entry.model,
                entry.score,
                entry.rationale,
                entry.confidence,
                entry.cost_usd,
                entry.created_at.isoformat(),
            ),
        )
        self._connection.commit()

    async def aclose(self) -> None:
        self._connection.close()


class PostgresJudgeCache:
    """Postgres cache used by the API and worker (and opt-in for the CLI)."""

    def __init__(self, database_url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(database_url)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self._ready = False
        self._lock = asyncio.Lock()

    async def _ensure_schema(self) -> None:
        if self._ready:
            return
        async with self._lock:
            if not self._ready:
                async with self._engine.begin() as connection:
                    await connection.run_sync(Base.metadata.create_all)
                self._ready = True

    async def get(self, key: str) -> CacheEntry | None:
        await self._ensure_schema()
        async with self._session_factory() as session:
            row = await session.scalar(select(JudgeCacheRow).where(JudgeCacheRow.hash == key))
        if row is None:
            return None
        return CacheEntry(
            hash=row.hash,
            response_hash=row.response_hash,
            rubric_hash=row.rubric_hash,
            model=row.model,
            score=row.score,
            rationale=row.rationale,
            confidence=row.confidence,
            cost_usd=row.cost_usd,
            created_at=row.created_at,
        )

    async def put(self, entry: CacheEntry) -> None:
        await self._ensure_schema()
        statement = (
            pg_insert(JudgeCacheRow)
            .values(
                hash=entry.hash,
                response_hash=entry.response_hash,
                rubric_hash=entry.rubric_hash,
                model=entry.model,
                score=entry.score,
                rationale=entry.rationale,
                confidence=entry.confidence,
                cost_usd=entry.cost_usd,
                created_at=entry.created_at,
            )
            .on_conflict_do_nothing(index_elements=[JudgeCacheRow.hash])
        )
        async with self._session_factory() as session:
            await session.execute(statement)
            await session.commit()

    async def aclose(self) -> None:
        await self._engine.dispose()


def build_judge_cache(
    *,
    backend: str,
    cache_dir: str | Path,
    database_url: str,
    no_cache: bool = False,
) -> JudgeCache:
    if no_cache:
        return NullJudgeCache()
    if backend == "postgres":
        return PostgresJudgeCache(database_url)
    if backend == "local":
        return LocalJudgeCache(Path(cache_dir) / "judge_cache.sqlite3")
    message = f"unknown judge cache backend: {backend!r}"
    raise ValueError(message)
