"""Retry policy and HTTP retry tests (no network)."""

from __future__ import annotations

import random

import httpx
import pytest
import respx

from evalgate.providers.base import (
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderServerError,
    ProviderTimeoutError,
)
from evalgate.providers.retry import RetryPolicy, post_with_retries

URL = "https://api.test/v1/chat/completions"


class Recorder:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def sleep(self, delay: float) -> None:
        self.delays.append(delay)


def test_delay_is_bounded_and_seeded() -> None:
    policy = RetryPolicy(base_delay_s=0.5, max_delay_s=8.0, jitter=0.25)
    first = policy.delay(1, retry_after=None, rng=random.Random(7))
    second = policy.delay(1, retry_after=None, rng=random.Random(7))
    assert first == second
    assert 0.375 <= first <= 0.625


def test_delay_doubles_per_attempt() -> None:
    policy = RetryPolicy(base_delay_s=1.0, max_delay_s=8.0, jitter=0.0)
    assert policy.delay(1, retry_after=None, rng=random.Random(0)) == 1.0
    assert policy.delay(2, retry_after=None, rng=random.Random(0)) == 2.0
    assert policy.delay(3, retry_after=None, rng=random.Random(0)) == 4.0
    assert policy.delay(9, retry_after=None, rng=random.Random(0)) == 8.0


def test_retry_after_wins_and_is_clamped() -> None:
    policy = RetryPolicy(max_delay_s=8.0)
    assert policy.delay(1, retry_after=2.5, rng=random.Random(0)) == 2.5
    assert policy.delay(1, retry_after=30.0, rng=random.Random(0)) == 8.0


@respx.mock
async def test_429_then_success_honours_retry_after() -> None:
    route = respx.post(URL).mock(
        side_effect=[
            httpx.Response(429, headers={"retry-after": "1.5"}),
            httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]}),
        ]
    )
    recorder = Recorder()
    response = await post_with_retries(
        httpx.AsyncClient(),
        URL,
        headers={},
        payload={},
        policy=RetryPolicy(max_attempts=3),
        sleep=recorder.sleep,
        rng=random.Random(0),
    )
    assert response.status_code == 200
    assert recorder.delays == [1.5]
    assert route.call_count == 2


@respx.mock
async def test_429_exhaustion_raises_rate_limit() -> None:
    route = respx.post(URL).mock(return_value=httpx.Response(429))
    recorder = Recorder()
    with pytest.raises(ProviderRateLimitError, match="rate limited after 2 attempts"):
        await post_with_retries(
            httpx.AsyncClient(),
            URL,
            headers={},
            payload={},
            policy=RetryPolicy(max_attempts=2),
            sleep=recorder.sleep,
            rng=random.Random(0),
        )
    assert route.call_count == 2
    assert len(recorder.delays) == 1


@respx.mock
async def test_5xx_then_success() -> None:
    route = respx.post(URL).mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    response = await post_with_retries(
        httpx.AsyncClient(),
        URL,
        headers={},
        payload={},
        policy=RetryPolicy(max_attempts=3),
        sleep=Recorder().sleep,
        rng=random.Random(0),
    )
    assert response.status_code == 200
    assert route.call_count == 2


@respx.mock
async def test_5xx_exhaustion_raises_server_error() -> None:
    respx.post(URL).mock(return_value=httpx.Response(500))
    with pytest.raises(ProviderServerError, match="after 2 attempts"):
        await post_with_retries(
            httpx.AsyncClient(),
            URL,
            headers={},
            payload={},
            policy=RetryPolicy(max_attempts=2),
            sleep=Recorder().sleep,
            rng=random.Random(0),
        )


@respx.mock
async def test_timeout_then_success() -> None:
    route = respx.post(URL).mock(
        side_effect=[
            httpx.TimeoutException("slow"),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    response = await post_with_retries(
        httpx.AsyncClient(),
        URL,
        headers={},
        payload={},
        policy=RetryPolicy(max_attempts=2),
        sleep=Recorder().sleep,
        rng=random.Random(0),
    )
    assert response.status_code == 200
    assert route.call_count == 2


@respx.mock
async def test_timeout_exhaustion_raises_timeout_error() -> None:
    respx.post(URL).mock(side_effect=httpx.ConnectTimeout("nope"))
    with pytest.raises(ProviderTimeoutError, match="unreachable after 1 attempts"):
        await post_with_retries(
            httpx.AsyncClient(),
            URL,
            headers={},
            payload={},
            policy=RetryPolicy(max_attempts=1),
            sleep=Recorder().sleep,
            rng=random.Random(0),
        )


@respx.mock
async def test_4xx_is_not_retried() -> None:
    route = respx.post(URL).mock(return_value=httpx.Response(400, text="bad request"))
    with pytest.raises(ProviderRequestError, match="HTTP 400"):
        await post_with_retries(
            httpx.AsyncClient(),
            URL,
            headers={},
            payload={},
            policy=RetryPolicy(max_attempts=4),
            sleep=Recorder().sleep,
            rng=random.Random(0),
        )
    assert route.call_count == 1
