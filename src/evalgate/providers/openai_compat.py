"""OpenAI-compatible chat-completions adapter.

Works with OpenAI, OpenRouter, vLLM, and Ollama's OpenAI-compatible endpoint: only the
Chat Completions shape is assumed. No SDK, no framework — the wire format is small enough
to own (see ADR-003).
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any

import httpx

from evalgate.models.case import Case
from evalgate.models.suite import ModelSpec
from evalgate.providers.base import (
    Completion,
    ProviderResponseError,
)
from evalgate.providers.pricing import PricingTable
from evalgate.providers.retry import (
    RetryPolicy,
    Sleep,
    _sleep_default,
    parse_json_response,
    post_with_retries,
)

logger = logging.getLogger(__name__)


def _token_count(usage: dict[str, Any], key: str) -> int:
    value = usage.get(key, 0)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        logger.warning("provider usage field %r missing or invalid; counting 0", key)
        return 0
    return value


class OpenAICompatibleProvider:
    """Provider for the ``POST /chat/completions`` contract."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
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
        headers = {"content-type": "application/json"}
        if self._api_key:
            headers["authorization"] = f"Bearer {self._api_key}"

        payload: dict[str, object] = {
            "model": model.name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": model.temperature,
            "max_tokens": model.max_tokens,
        }

        started = time.perf_counter()
        response = await post_with_retries(
            self._client,
            f"{self._base_url}/chat/completions",
            headers=headers,
            payload=payload,
            policy=self._policy,
            sleep=self._sleep,
            rng=self._rng,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)

        body = parse_json_response(response)
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderResponseError("provider response is missing choices")
        first = choices[0]
        if not isinstance(first, dict):
            raise ProviderResponseError("provider choice is not an object")
        message = first.get("message")
        if not isinstance(message, dict):
            raise ProviderResponseError("provider choice is missing a message object")
        text = message.get("content")
        if not isinstance(text, str):
            raise ProviderResponseError("provider message content is not a string")

        usage = body.get("usage")
        if not isinstance(usage, dict):
            logger.warning("provider response is missing usage; counting 0 tokens")
            usage = {}
        tokens_in = _token_count(usage, "prompt_tokens")
        tokens_out = _token_count(usage, "completion_tokens")

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
