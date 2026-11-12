# ADR-003: Hand-written provider adapters, no agent framework

**Status:** accepted · **Phase:** E2

## Context

The project needs two model providers: OpenAI-compatible Chat Completions and Anthropic
Messages. Both are small HTTP+JSON contracts. Candidate implementations:

1. LangChain / LlamaIndex wrappers.
2. Provider SDKs (`openai`, `anthropic`).
3. Hand-written adapters on `httpx`.

The rest of the system depends on precise control over retries, timeouts, token accounting,
cost, and error classification. Eval correctness depends on knowing exactly what was sent and
what came back.

## Decision

Own the adapters. Each provider implements one method:

```python
async def complete(*, prompt: str, case: Case, model: ModelSpec) -> Completion: ...
```

`Completion` carries text, tokens in/out, cost, latency, model, and the raw body. A shared
`RetryPolicy` handles 429/5xx/timeouts with exponential backoff, bounded jitter, and
`Retry-After`. Failures are typed (`ProviderRateLimitError`, `ProviderTimeoutError`,
`ProviderResponseError`, …) so the runner can distinguish a failed verdict from a broken run.

## Consequences

- **Pros:** explicit retry and cost accounting; no framework upgrade churn; an OpenAI-compatible
  server (OpenRouter, vLLM, Ollama) works by changing `base_url`; tests use `respx` against the
  real wire format; the dependency surface stays small.
- **Cons:** we maintain parsing for two response shapes; streaming, tool calls, and multimodal
  inputs are not covered; provider-specific features need explicit adapter work.
- **Con:** no automatic fallback across providers. That is deliberate: a fallback changes the
  model under test and invalidates the comparison.

## When to revisit

If the product needs tool calls, streaming, or a provider matrix with automatic routing, adopt
an SDK per provider (not a general agent framework) and keep the `Completion` boundary. The
runner, metrics, and reports do not depend on the transport.

## Alternatives considered

- **LangChain:** heavy dependency tree, its own callbacks/retry semantics, and abstractions that
  obscure token usage. We would spend more time pinning versions than writing two adapters.
- **Official SDKs:** good, but their retry layers are opinionated and harder to inject in tests;
  two SDKs plus their transitive dependencies outweigh ~120 lines of `httpx` per adapter.
- **LiteLLM:** convenient proxy, but another moving part in the cost/accounting path and a
  network hop we do not need.
