"""SQLAlchemy models. The full run schema lands in phase E4; the judge cache is shared."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for every EvalGate table."""


class JudgeCacheRow(Base):
    """Content-addressed judge verdict, keyed by response + rubric + model + prompt version."""

    __tablename__ = "judge_cache"

    hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    response_hash: Mapped[str] = mapped_column(String(64), index=True)
    rubric_hash: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128), index=True)
    score: Mapped[int] = mapped_column(Integer)
    rationale: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
