"""Per-model pricing table used to account for completion cost.

Prices are USD per one million tokens and carry an ``effective_date`` so published cost
numbers can be traced to a date. Unknown models report zero cost with a warning instead of
crashing a run.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from importlib.resources import files
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

_PRECISION = Decimal("0.000001")


class PricingEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_per_1m_usd: Decimal = Field(ge=0)
    output_per_1m_usd: Decimal = Field(ge=0)


class PricingTable(BaseModel):
    """A dated table of model prices."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    effective_date: date
    models: dict[str, PricingEntry]

    def cost(self, model: str, *, tokens_in: int, tokens_out: int) -> Decimal:
        entry = self.models.get(model)
        if entry is None:
            logger.warning("unknown model %r in pricing table; reporting cost 0", model)
            return Decimal(0)
        raw = (entry.input_per_1m_usd * tokens_in + entry.output_per_1m_usd * tokens_out) / Decimal(
            1_000_000
        )
        return raw.quantize(_PRECISION, rounding=ROUND_HALF_UP)

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> PricingTable:
        return cls.model_validate(payload)

    @classmethod
    def default(cls) -> PricingTable:
        resource = files("evalgate.providers").joinpath("pricing.yaml")
        payload = yaml.safe_load(resource.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            message = "providers/pricing.yaml must contain a mapping"
            raise ValueError(message)
        return cls.from_mapping(payload)
