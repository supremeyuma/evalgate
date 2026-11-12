"""Provider adapters and the provider factory."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlparse

import httpx

from evalgate.config import Settings, get_settings
from evalgate.models.suite import ModelSpec
from evalgate.providers.anthropic import AnthropicProvider
from evalgate.providers.base import (
    Completion,
    Provider,
    ProviderConfigError,
    ProviderError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderResponseError,
    ProviderServerError,
    ProviderTimeoutError,
)
from evalgate.providers.mock import MockProvider, ReplayProvider
from evalgate.providers.openai_compat import OpenAICompatibleProvider
from evalgate.providers.pricing import PricingEntry, PricingTable
from evalgate.providers.retry import RetryPolicy

__all__ = [
    "AnthropicProvider",
    "Completion",
    "MockProvider",
    "OpenAICompatibleProvider",
    "PricingEntry",
    "PricingTable",
    "Provider",
    "ProviderConfigError",
    "ProviderError",
    "ProviderRateLimitError",
    "ProviderRequestError",
    "ProviderResponseError",
    "ProviderServerError",
    "ProviderTimeoutError",
    "ReplayProvider",
    "RetryPolicy",
    "build_provider",
]


def build_provider(
    model: ModelSpec,
    *,
    force_mock: bool = False,
    settings: Settings | None = None,
    mock_fixtures: Mapping[str, str] | None = None,
    replay_dir: str | Path | None = None,
    client: httpx.AsyncClient | None = None,
    mock_latency_ms: int = 0,
) -> Provider:
    """Construct the provider a suite asks for.

    ``force_mock`` (the CLI's ``--mock``) wins over the suite's provider so every demo and
    test can run without keys or network.
    """

    if replay_dir is not None:
        return ReplayProvider(replay_dir)
    if force_mock or model.provider == "mock":
        return MockProvider(mock_fixtures, simulated_latency_ms=mock_latency_ms)

    config = settings or get_settings()

    if model.provider == "openai-compatible":
        base_url = model.base_url or config.openai_base_url
        api_key = config.openai_api_key
        host = urlparse(base_url).hostname or ""
        if host == "api.openai.com" and not api_key:
            message = (
                "OPENAI_API_KEY is not set; use --mock, set the key, or point "
                "model.base_url at a local OpenAI-compatible server"
            )
            raise ProviderConfigError(message)
        policy = RetryPolicy(max_attempts=config.provider_max_attempts)
        return OpenAICompatibleProvider(
            base_url=base_url,
            api_key=api_key,
            client=client,
            retry_policy=policy,
            timeout_s=config.provider_timeout_s,
        )

    if model.provider == "anthropic":
        api_key = config.anthropic_api_key
        if not api_key:
            message = "ANTHROPIC_API_KEY is not set; use --mock or set the key"
            raise ProviderConfigError(message)
        policy = RetryPolicy(max_attempts=config.provider_max_attempts)
        return AnthropicProvider(
            base_url=config.anthropic_base_url,
            api_key=api_key,
            client=client,
            retry_policy=policy,
            timeout_s=config.provider_timeout_s,
        )

    message = f"unsupported provider: {model.provider}"  # type: ignore[unreachable]
    raise ProviderConfigError(message)
