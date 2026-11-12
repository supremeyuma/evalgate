"""Provider protocol, completion model, and typed provider errors."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from evalgate.models.case import Case
from evalgate.models.suite import ModelSpec


class Completion(BaseModel):
    """A single model completion plus the accounting needed by metrics and reports."""

    model_config = ConfigDict(extra="forbid")

    text: str
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    cost_usd: Decimal = Field(ge=0)
    latency_ms: int = Field(ge=0)
    model: str
    raw: dict[str, Any] | None = None


@runtime_checkable
class Provider(Protocol):
    """Minimal interface every provider adapter implements."""

    async def complete(self, *, prompt: str, case: Case, model: ModelSpec) -> Completion: ...

    async def aclose(self) -> None: ...


class ProviderError(Exception):
    """Base class for provider failures surfaced by an adapter."""


class ProviderConfigError(ProviderError):
    """The adapter is missing configuration (for example an API key)."""


class ProviderRequestError(ProviderError):
    """The provider rejected the request; retrying will not help."""


class ProviderRateLimitError(ProviderError):
    """The provider kept returning 429 after every retry."""


class ProviderServerError(ProviderError):
    """The provider kept returning 5xx after every retry."""


class ProviderTimeoutError(ProviderError):
    """The provider timed out after every retry."""


class ProviderResponseError(ProviderError):
    """The provider response could not be parsed into a completion."""
