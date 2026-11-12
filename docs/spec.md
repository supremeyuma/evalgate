# EvalGate — CI Quality Gate for LLM Outputs

**One line:** A regression-testing system for LLM features: define an eval suite in YAML,
run it against any provider, fail the pull request when quality drops below threshold.

**Why this is the flagship:** almost every "AI engineer" portfolio is a chatbot. Almost
none have **evals, judges, thresholds, cost/latency tracking, and CI enforcement**. This
is the single strongest signal you can send to a company shipping LLM features.

## What it proves

- Applied AI: prompt/rubric design, LLM-as-judge, dataset curation, statistical thinking
- Backend: FastAPI, background workers, Postgres, caching, rate limiting, retries
- DevOps: GitHub Action, PR comments, artifact reports
- Product judgement: what "quality" means, when a 2% drop is noise
- Python depth: async, typing, Pydantic v2, testing with recorded fixtures

## Scope

**In:**
- Eval suite defined in YAML (`cases`, `metrics`, `thresholds`)
- Provider adapters: OpenAI-compatible (works with OpenRouter/Ollama) + Anthropic
- Metrics: `exact_match`, `contains`, `json_schema_valid`, `semantic_similarity`,
  `llm_judge` (rubric scored 1–5 with rationale), `latency_ms`, `cost_usd`
- Judge caching (content hash) so re-runs are cheap
- CLI: `evalgate run suite.yaml --baseline main`
- GitHub Action: run on PR, comment summary, fail on regression
- Report: HTML + JSON artifacts; per-case pass/fail diff vs baseline
- Cost/latency budget assertions

**Out:** a web UI, fine-tuning, dataset annotation tooling, multi-tenant billing,
agent tracing platform (link to Langfuse/LangSmith instead — mention them in tradeoffs).

## Stack

- FastAPI + Pydantic v2 + SQLAlchemy 2.0 + Alembic + Postgres
- Redis + ARQ for parallel eval runs (bounded concurrency, retry on 429)
- `httpx` provider clients (hand-written adapters, no LangChain — explain why in an ADR)
- `pytest` + `vcrpy`/recorded fixtures so the test suite never calls a live model
- GitHub Actions + `gh` API (or a tiny GitHub App later)
- Docker, Ruff, mypy strict, `uv`

## Eval suite format (design it first — this is the product)

```yaml
name: support-reply-quality
model: { provider: openai-compatible, name: gpt-4.1-mini, temperature: 0 }
prompt: prompts/support.md
cases_file: datasets/support.jsonl        # {id, input, expected?, context?}
metrics:
  - type: json_schema_valid
    schema: schemas/reply.json
  - type: llm_judge
    rubric: rubrics/helpfulness.md        # 1-5 + rationale
    threshold: 4.0
  - type: contains
    value: "refund"
limits:
  max_cost_usd: 0.50
  max_p95_latency_ms: 4000
regression:
  max_pass_rate_drop: 0.03                # 3 percentage points
```

## Data model

```
suites(id, name, yaml, created_at)
runs(id, suite_id, commit_sha, baseline_run_id, status,
     pass_rate, cost_usd, p95_latency_ms, started_at, finished_at)
results(id, run_id, case_id, metric, score, passed, latency_ms, cost_usd,
        judge_output jsonb, response text)
judge_cache(hash, model, rubric_hash, score, rationale, created_at)
```

## Milestones

### M0 — Domain design (2–3 days)
- [ ] Write the YAML schema and 2 example suites (one classification, one generation)
- [ ] Curate 30–50 real cases; write 2 rubrics with explicit scoring anchors
- [ ] Decide: per-case pass/fail vs aggregate. Document in an ADR.

### M1 — Runner + adapters (4 days)
- [ ] Provider adapter interface: `complete(prompt, case) -> {text, tokens, cost, latency}`
- [ ] OpenAI-compatible + Anthropic adapters with timeout/retry/429 handling
- [ ] Deterministic metrics + JSON schema validation
- [ ] CLI runs a suite and prints a table; exit code 1 on failure
- [ ] Fixture-recorded tests; no network in CI

### M2 — Judges (4–5 days)
- [ ] Rubric prompt template with anchors + JSON output contract
- [ ] Score normalization (1–5 → 0–1), rationale storage, disagreement handling
- [ ] Judge caching by `(response_hash, rubric_hash, model)`
- [ ] Calibration: run 2 judges on 30 cases, measure agreement, report it
- [ ] Tests: malformed judge output, refusal, out-of-range score → retry/repair path

### M3 — Persistence + concurrency (3 days)
- [ ] Postgres storage of runs/results; parallel worker with bounded concurrency
- [ ] Cost and p95 latency aggregation; per-metric confidence interval on pass rate
- [ ] Baseline comparison logic; "regression" definition in code + ADR

### M4 — CI integration (3–4 days)
- [ ] GitHub Action (composite) + example consumer repo
- [ ] PR comment: table of metric, baseline, current, delta, verdict
- [ ] Artifacts: HTML report + JSON; link in comment
- [ ] Fails the check only on real regressions; documents flaky-run policy

### M5 — Polish (3 days)
- [ ] README with before/after PR screenshot, architecture, cost-per-run number
- [ ] Demo: deliberately break a prompt, show the gate catching it
- [ ] Case study: "how I decide an LLM feature is good enough to ship"
- [ ] Publish the Action to the Marketplace (free, huge distribution win)

## Demo script (for interviews)

> "Teams ship prompt changes with no tests. EvalGate turns a golden dataset into a CI
> gate. This suite has 47 cases; the judge is a rubric-scored model with anchors, cached
> by content hash so re-runs cost cents. When I weakened the system prompt, pass rate
> fell from 94% to 81% and the cost budget tripped — the PR was blocked with a table
> showing exactly which cases regressed. Here's the Action, here's the calibration
> report showing 87% agreement between two judges."

## Stretch

- Deterministic replay with `temperature=0` + seed pinning
- Pairwise comparison mode (A/B prompts) instead of absolute scores
- MCP server exposing `run_suite` and `get_regressions` tools
- Multi-model matrix ("same suite across 3 models, cost/quality frontier")

## Traps to avoid

- Reporting a single average score. Per-case diffs are the product.
- Letting an LLM judge grade without anchors; you'll get noise, not signal.
- Treating a 1–2% drop as real. Compute the interval, say so in the README.
- Calling live APIs in your test suite. Record fixtures.
- Building a UI first. The CLI + CI comment is the value.
