"""OpenAI-compatible and Anthropic adapter tests using respx (no network)."""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import respx

from evalgate.config import Settings
from evalgate.models.case import Case
from evalgate.models.suite import ModelSpec
from evalgate.providers import (
    AnthropicProvider,
    MockProvider,
    OpenAICompatibleProvider,
    ProviderConfigError,
    ProviderResponseError,
    ReplayProvider,
    build_provider,
)

OPENAI_URL = "https://api.test/v1/chat/completions"
ANTHROPIC_URL = "https://anthropic.test/v1/messages"


def _openai_body(text: str = "hello", *, usage: bool = True) -> dict[str, object]:
    body: dict[str, object] = {
        "model": "gpt-4.1-mini",
        "choices": [{"message": {"role": "assistant", "content": text}}],
    }
    if usage:
        body["usage"] = {"prompt_tokens": 1000, "completion_tokens": 500}
    return body


@respx.mock
async def test_openai_success_sends_expected_payload(case: Case, model: ModelSpec) -> None:
    route = respx.post(OPENAI_URL).mock(return_value=httpx.Response(200, json=_openai_body()))
    provider = OpenAICompatibleProvider(base_url="https://api.test/v1", api_key="test-key")
    completion = await provider.complete(prompt="Say hi", case=case, model=model)
    await provider.aclose()

    assert completion.text == "hello"
    assert completion.tokens_in == 1000
    assert completion.tokens_out == 500
    assert completion.cost_usd == Decimal("0.001200")
    request = route.calls[0].request
    assert request.headers["authorization"] == "Bearer test-key"
    payload = json.loads(request.content)
    assert payload["model"] == "gpt-4.1-mini"
    assert payload["temperature"] == 0
    assert payload["messages"] == [{"role": "user", "content": "Say hi"}]


@respx.mock
async def test_openai_missing_usage_warns_and_counts_zero(
    case: Case, model: ModelSpec, caplog: pytest.LogCaptureFixture
) -> None:
    respx.post(OPENAI_URL).mock(return_value=httpx.Response(200, json=_openai_body(usage=False)))
    provider = OpenAICompatibleProvider(base_url="https://api.test/v1", api_key="test-key")
    with caplog.at_level(logging.WARNING):
        completion = await provider.complete(prompt="x", case=case, model=model)
    await provider.aclose()

    assert completion.tokens_in == 0
    assert completion.tokens_out == 0
    assert completion.cost_usd == Decimal(0)
    assert "missing usage" in caplog.text


@respx.mock
async def test_openai_malformed_json_raises(case: Case, model: ModelSpec) -> None:
    respx.post(OPENAI_URL).mock(return_value=httpx.Response(200, text="<html>not json</html>"))
    provider = OpenAICompatibleProvider(base_url="https://api.test/v1", api_key="k")
    with pytest.raises(ProviderResponseError, match="invalid JSON"):
        await provider.complete(prompt="x", case=case, model=model)
    await provider.aclose()


@respx.mock
async def test_openai_missing_choices_raises(case: Case, model: ModelSpec) -> None:
    respx.post(OPENAI_URL).mock(return_value=httpx.Response(200, json={"choices": []}))
    provider = OpenAICompatibleProvider(base_url="https://api.test/v1", api_key="k")
    with pytest.raises(ProviderResponseError, match="missing choices"):
        await provider.complete(prompt="x", case=case, model=model)
    await provider.aclose()


@respx.mock
async def test_openai_non_string_content_raises(case: Case, model: ModelSpec) -> None:
    respx.post(OPENAI_URL).mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": None}}]})
    )
    provider = OpenAICompatibleProvider(base_url="https://api.test/v1", api_key="k")
    with pytest.raises(ProviderResponseError, match="not a string"):
        await provider.complete(prompt="x", case=case, model=model)
    await provider.aclose()


@respx.mock
async def test_anthropic_success(case: Case) -> None:
    route = respx.post(ANTHROPIC_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "claude-sonnet-4-5",
                "content": [
                    {"type": "text", "text": "Hello "},
                    {"type": "text", "text": "world"},
                ],
                "usage": {"input_tokens": 1_000_000, "output_tokens": 0},
            },
        )
    )
    provider = AnthropicProvider(api_key="key", base_url="https://anthropic.test")
    model = ModelSpec(provider="anthropic", name="claude-sonnet-4-5", max_tokens=64)
    completion = await provider.complete(prompt="hi", case=case, model=model)
    await provider.aclose()

    assert completion.text == "Hello world"
    assert completion.cost_usd == Decimal("3.000000")
    request = route.calls[0].request
    assert request.headers["x-api-key"] == "key"
    assert request.headers["anthropic-version"] == "2023-06-01"


@respx.mock
async def test_anthropic_no_text_blocks_raises(case: Case) -> None:
    respx.post(ANTHROPIC_URL).mock(return_value=httpx.Response(200, json={"content": []}))
    provider = AnthropicProvider(api_key="key", base_url="https://anthropic.test")
    model = ModelSpec(provider="anthropic", name="claude-sonnet-4-5")
    with pytest.raises(ProviderResponseError, match="no text blocks"):
        await provider.complete(prompt="hi", case=case, model=model)
    await provider.aclose()


def _settings(**overrides: object) -> Settings:
    payload: dict[str, object] = {
        "openai_api_key": None,
        "anthropic_api_key": None,
    }
    payload.update(overrides)
    return Settings(_env_file=None, **payload)  # type: ignore[arg-type]


def test_factory_forces_mock() -> None:
    model = ModelSpec(provider="openai-compatible", name="gpt-4.1-mini")
    provider = build_provider(model, force_mock=True, settings=_settings())
    assert isinstance(provider, MockProvider)


def test_factory_honours_declared_mock() -> None:
    model = ModelSpec(provider="mock", name="m")
    assert isinstance(build_provider(model, settings=_settings()), MockProvider)


def test_factory_replay(tmp_path: Path) -> None:
    model = ModelSpec(provider="mock", name="m")
    provider = build_provider(model, settings=_settings(), replay_dir=str(tmp_path))
    assert isinstance(provider, ReplayProvider)


def test_factory_openai_requires_key_for_public_endpoint() -> None:
    model = ModelSpec(provider="openai-compatible", name="gpt-4.1-mini")
    with pytest.raises(ProviderConfigError, match="OPENAI_API_KEY"):
        build_provider(model, settings=_settings())


def test_factory_openai_allows_keyless_local_endpoint() -> None:
    model = ModelSpec(
        provider="openai-compatible",
        name="llama3",
        base_url="http://localhost:11434/v1",
    )
    provider = build_provider(model, settings=_settings())
    assert isinstance(provider, OpenAICompatibleProvider)


def test_factory_anthropic_requires_key() -> None:
    model = ModelSpec(provider="anthropic", name="claude-sonnet-4-5")
    with pytest.raises(ProviderConfigError, match="ANTHROPIC_API_KEY"):
        build_provider(model, settings=_settings())
