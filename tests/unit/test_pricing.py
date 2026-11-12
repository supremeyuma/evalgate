"""Pricing table tests."""

from __future__ import annotations

import logging
from decimal import Decimal

import pytest
from pydantic import ValidationError

from evalgate.providers.pricing import PricingEntry, PricingTable


def test_default_table_loads() -> None:
    table = PricingTable.default()
    assert table.version == 1
    assert table.effective_date.isoformat() == "2026-11-01"
    assert "gpt-4.1-mini" in table.models


def test_cost_math_one_million_tokens() -> None:
    table = PricingTable.default()
    cost = table.cost("gpt-4.1-mini", tokens_in=1_000_000, tokens_out=1_000_000)
    assert cost == Decimal("2.000000")


def test_cost_math_small_request() -> None:
    table = PricingTable.from_mapping(
        {
            "version": 1,
            "effective_date": "2026-01-01",
            "models": {
                "m": {"input_per_1m_usd": 2, "output_per_1m_usd": 8},
            },
        }
    )
    cost = table.cost("m", tokens_in=1000, tokens_out=500)
    assert cost == Decimal("0.006000")


def test_cost_quantizes_to_six_places() -> None:
    table = PricingTable.from_mapping(
        {
            "version": 1,
            "effective_date": "2026-01-01",
            "models": {"m": {"input_per_1m_usd": 0.4, "output_per_1m_usd": 1.6}},
        }
    )
    assert table.cost("m", tokens_in=1, tokens_out=0) == Decimal("0.000000")


def test_unknown_model_warns_and_costs_zero(
    caplog: pytest.LogCaptureFixture,
) -> None:
    table = PricingTable.default()
    with caplog.at_level(logging.WARNING):
        cost = table.cost("mystery-model", tokens_in=100, tokens_out=100)
    assert cost == Decimal(0)
    assert "unknown model" in caplog.text


def test_negative_prices_rejected() -> None:
    with pytest.raises(ValidationError):
        PricingEntry(input_per_1m_usd=Decimal("-1"), output_per_1m_usd=Decimal("1"))
