# EvalGate 1.0.0

EvalGate is a CI quality gate for LLM features: define an eval suite in YAML, run it against
any provider, and fail the pull request when quality drops below threshold.

## Highlights

- **Strict suite contract** — Pydantic `extra=forbid`, path-traversal protection, generated
  JSON Schema, `evalgate validate` / `evalgate schema`.
- **Providers** — OpenAI-compatible (OpenAI, OpenRouter, vLLM, Ollama) and Anthropic, with
  retries, timeouts, `Retry-After`, typed errors, and a dated pricing table.
- **Metrics** — exact match, contains, JSON Schema, regex, latency, cost, and an anchored
  LLM judge with one repair attempt, refusal handling, and a content-addressed cache.
- **Regression rule** — pass-rate drop beyond the threshold *and* non-overlapping Wilson 95%
  intervals; small samples never fail. Hard cost/latency limits fail independently.
- **Reports** — stable JSON, self-contained HTML with per-case diffs and judge rationales,
  and an idempotent PR comment.
- **GitHub Action** — composite action with artifact upload, baseline-by-ref, and read-only
  fork handling.
- **Demo stack** — FastAPI, ARQ worker, Postgres, Redis, Alembic, and compose on reserved
  ports 5434/6381/8001.

## Measured (mock provider, 2026-11-12)

- 40-case support suite: 100%, Wilson 95% CI 91.2–100%.
- Cold run 160 ms with 40 judge calls; warm run 33 ms with 40/40 cache hits.
- 235 tests, 91.4% coverage, mypy strict, zero live network calls.
- 13/13 walkthrough steps, actionlint, Alembic up/down, Docker build, and compose API run.

Live cost and quality numbers are intentionally absent: no provider key was used. The README
labels the live-cost estimate and the committed calibration as mock-derived.

## Deferred

Demo GIF recording, Marketplace listing publish, and a hosted demo URL are human steps; the
tape, listing instructions, and local demo are committed.
