"""Retry policy for provider HTTP calls.

Backoff is exponential with bounded jitter. ``Retry-After`` wins when the provider sends
it. Tests inject the sleep function and a seeded RNG so timing assertions are exact.
"""

from __future__ import annotations

import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx

from evalgate.providers.base import (
    ProviderError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderResponseError,
    ProviderServerError,
    ProviderTimeoutError,
)

Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class RetryPolicy:
    """How many attempts to make and how long to wait between them."""

    max_attempts: int = 4
    base_delay_s: float = 0.5
    max_delay_s: float = 8.0
    jitter: float = 0.25

    def delay(self, attempt: int, *, retry_after: float | None, rng: random.Random) -> float:
        if retry_after is not None:
            return max(0.0, min(retry_after, self.max_delay_s))
        raw = min(self.max_delay_s, self.base_delay_s * (2 ** (attempt - 1)))
        low = raw * (1 - self.jitter)
        high = raw * (1 + self.jitter)
        return float(low + (high - low) * rng.random())


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


async def _sleep_default(delay: float) -> None:  # pragma: no cover - real clock
    import asyncio

    await asyncio.sleep(delay)


async def post_with_retries(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, object],
    policy: RetryPolicy,
    sleep: Sleep = _sleep_default,
    rng: random.Random | None = None,
) -> httpx.Response:
    """POST JSON, retrying 429/5xx/timeouts with exponential backoff."""

    generator = rng or random.Random()  # noqa: S311 - jitter only, not a security token
    last_status: int | None = None

    for attempt in range(1, policy.max_attempts + 1):
        try:
            response = await client.post(url, headers=headers, json=payload)
        except (httpx.TimeoutException, httpx.TransportError) as error:
            if attempt >= policy.max_attempts:
                message = f"provider unreachable after {attempt} attempts: {error}"
                raise ProviderTimeoutError(message) from error
            await sleep(policy.delay(attempt, retry_after=None, rng=generator))
            continue

        last_status = response.status_code
        if response.status_code == 429:
            if attempt >= policy.max_attempts:
                message = f"provider rate limited after {attempt} attempts (HTTP 429)"
                raise ProviderRateLimitError(message)
            await sleep(policy.delay(attempt, retry_after=_retry_after(response), rng=generator))
            continue

        if 500 <= response.status_code < 600:
            if attempt >= policy.max_attempts:
                message = f"provider failed after {attempt} attempts (HTTP {response.status_code})"
                raise ProviderServerError(message)
            await sleep(policy.delay(attempt, retry_after=_retry_after(response), rng=generator))
            continue

        if response.status_code >= 400:
            snippet = response.text[:200].replace("\n", " ")
            message = f"provider rejected the request (HTTP {response.status_code}): {snippet}"
            raise ProviderRequestError(message)

        return response

    message = f"provider call exhausted retries (last HTTP {last_status})"
    raise ProviderError(message)


def parse_json_response(response: httpx.Response) -> dict[str, object]:
    """Parse a provider response body, raising a typed error on malformed JSON."""

    try:
        payload = response.json()
    except ValueError as error:
        raise ProviderResponseError(f"provider returned invalid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ProviderResponseError("provider returned a non-object JSON body")
    return payload
