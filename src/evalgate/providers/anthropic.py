"""Anthropic Messages API adapter."""

from __future__ import annotations

import logging
import random
import time
from typing import Any

import httpx

from evalgate.models.case import Case
from evalgate.models.suite import ModelSpec
from evalgate.providers.base import Completion, ProviderResponseError
from evalgate.providers.pricing import PricingTable
from evalgate.providers.retry import (
    RetryPolicy,
    Sleep,
    _sleep_default,
    parse_json_response,
    post_with_retries,
)

logger = logging.getLogger(__name__)

ANTHROPIC_VERSION = "2023-06-01"


def _token_count(usage: dict[str, Any], key: str) -> int:
    value = usage.get(key, 0)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        logger.warning("provider usage field %r missing or invalid; counting 0", key)
        return 0
    return value


def _extract_text(body: dict[str, Any]) -> str:
    content = body.get("content")
    if not isinstance(content, list):
        raise ProviderResponseError("anthropic response is missing content blocks")
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
    if not parts:
        raise ProviderResponseError("anthropic response contains no text blocks")
    return "".join(parts)


class AnthropicProvider:
    """Provider for ``POST /v1/messages``."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.anthropic.com",
        client: httpx.AsyncClient | None = None,
        pricing: PricingTable | None = None,
        retry_policy: RetryPolicy | None = None,
        timeout_s: float = 60.0,
        sleep: Sleep | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=timeout_s)
        self._owns_client = client is None
        self._pricing = pricing or PricingTable.default()
        self._policy = retry_policy or RetryPolicy()
        self._sleep = sleep or _sleep_default
        self._rng = rng

    async def complete(self, *, prompt: str, case: Case, model: ModelSpec) -> Completion:
        headers = {
            "content-type": "application/json",
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        }
        payload: dict[str, object] = {
            "model": model.name,
            "max_tokens": model.max_tokens,
            "temperature": model.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }

        started = time.perf_counter()
        response = await post_with_retries(
            self._client,
            f"{self._base_url}/v1/messages",
            headers=headers,
            payload=payload,
            policy=self._policy,
            sleep=self._sleep,
            rng=self._rng,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)

        body = parse_json_response(response)
        text = _extract_text(body)

        usage = body.get("usage")
        if not isinstance(usage, dict):
            logger.warning("anthropic response is missing usage; counting 0 tokens")
            usage = {}
        tokens_in = _token_count(usage, "input_tokens")
        tokens_out = _token_count(usage, "output_tokens")

        return Completion(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=self._pricing.cost(model.name, tokens_in=tokens_in, tokens_out=tokens_out),
            latency_ms=latency_ms,
            model=str(body.get("model") or model.name),
            raw=body,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
