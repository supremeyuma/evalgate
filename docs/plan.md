# EvalGate — Execution Plan (Project 3 of 4)

> **Bootstrap note:** this repository already exists with git, an MIT license, and a private
> remote. Skip the folder/git/remote steps in Phase E0; start with the tooling tasks. See
> `AGENTS.md` for the working contract and reserved ports.

**Spec:** `projects/p2-evalgate.md` · **Rubric:** `projects/00-project-rubric.md`
**Read first:** `execution/00-master-plan.md`. Follow its branch/commit/phase conventions
and release gate.

**Mission:** a regression-testing system for LLM features: define an eval suite in YAML, run
it against any provider, fail the pull request when quality drops below threshold.

**Working days:** 16–20. **Repo:** `../evalgate` (`C:\Users\Supreme\repos\evalgate`).
**Start only after StatusBeam is tagged `v1.0.0` and its release gate passes.**

**Stack is frozen:** Python 3.12, uv, Pydantic v2, FastAPI, SQLAlchemy 2.0 async, Alembic,
Postgres 16, Redis 7, ARQ, httpx, Typer + Rich, PyYAML, jsonschema, Jinja2, pytest +
pytest-asyncio + respx + vcrpy + Hypothesis, Ruff, mypy strict, Docker, GitHub Actions.

> **The product is the eval semantics, not the UI.** Per-case diffs, judge caching, and a
> defensible regression rule are the core. No live API calls in tests, ever.

---

## 1. Target architecture

```
suite.yaml ──▶ loader/validator (Pydantic, extra=forbid)
                    │
                    ▼
             runner (bounded concurrency)
              │        │            │
        provider    metrics      judge (rubric prompt)
        adapter     registry     ├── cache: hash(response, rubric, model, prompt ver)
      (OpenAI-      ├ exact     └── repair/retry on malformed JSON
       compat /     ├ contains
       Anthropic)   ├ json_schema
                    ├ regex
                    ├ latency
                    └ cost
                    │
                    ▼
          results ──▶ Postgres (runs/results/judge_cache)
                    ├──▶ CLI table (exit 0/1/2)
                    ├──▶ JSON + HTML report
                    └──▶ GitHub Action → PR comment + check verdict
```

Baseline/regression rule (documented in ADR-002):
- A case passes only if every required metric passes.
- Run `pass_rate = passed / total`.
- Regression = (baseline pass rate − current pass rate) > `max_pass_rate_drop` **and** the
  Wilson 95% intervals do not overlap in the direction of improvement. The second condition
  prevents noise-driven failures.
- Hard limits (`max_cost_usd`, `max_p95_latency_ms`) fail the run regardless of pass rate.

### Repository layout (final)

```
evalgate/
  src/evalgate/
    __init__.py cli.py config.py
    models/      suite.py case.py result.py report.py
    providers/   base.py openai_compat.py anthropic.py mock.py pricing.py
    metrics/     base.py exact.py contains.py json_schema.py regex.py latency.py cost.py
    judges/      rubric.py parser.py cache.py calibration.py
    runner/      engine.py concurrency.py baseline.py regression.py
    report/      json_report.py html_report.py pr_comment.py templates/
    storage/     db.py models.py repository.py migrations (alembic/)
    worker/      settings.py tasks.py
    api/         main.py routes.py deps.py
  examples/
    support/     suite.yaml prompts/ datasets/ rubrics/ schemas/
    classification/ suite.yaml ...
    consumer/    .github/workflows/evalgate.yml suite.yaml
  action.yml
  tests/         unit/ integration/ fixtures/ cassettes/
  docs/          roadmap.md eval-suite-spec.md calibration.md case-study.md
                 failure-modes.md security.md adr/ demo.gif
  scripts/       verify.ps1 walkthrough.ps1 demo_regression.py
  Dockerfile docker-compose.yml pyproject.toml .env.example .github/workflows/ci.yml
```

---

## 2. Phase E0 — Bootstrap (0.5 day)

1. Create `../evalgate`:
   ```powershell
   $name = "evalgate"
   $dest = Join-Path (Split-Path -Parent (Get-Location)) $name
   New-Item -ItemType Directory -Path $dest -Force
   Set-Location $dest
   git init -b main
   git config core.autocrlf false
   ```
2. MIT `LICENSE`, `.gitattributes`, `.gitignore` (`.venv/`, caches, `.env*`,
   `tests/cassettes/*.yaml` only if intentionally large, `reports/`), README stub.
3. Project:
   ```powershell
   uv init --python 3.12 --name evalgate --vcs none
   Remove-Item main.py -ErrorAction SilentlyContinue
   uv add pydantic pydantic-settings pyyaml jsonschema jinja2 typer rich httpx `
     "sqlalchemy[asyncio]" asyncpg alembic redis arq fastapi "uvicorn[standard]"
   uv add --dev pytest pytest-asyncio pytest-cov respx vcrpy hypothesis ruff mypy `
     types-pyyaml testcontainers
   ```
4. `pyproject.toml`: `[project.scripts] evalgate = "evalgate.cli:app"`; Ruff (line 100,
   `py312`, `E,F,I,UP,B,SIM,ASYNC,RUF,S`); mypy strict with `pydantic.mypy`; pytest
   `asyncio_mode=auto`, `--strict-markers`; coverage `fail_under=80` for
   `src/evalgate/{runner,judges,metrics}`.
5. Seed `.env.example`:
   ```
   DATABASE_URL=postgresql+asyncpg://evalgate:evalgate@localhost:5432/evalgate
   REDIS_URL=redis://localhost:6379/0
   OPENAI_API_KEY=
   OPENAI_BASE_URL=https://api.openai.com/v1
   ANTHROPIC_API_KEY=
   EVALGATE_API_KEY=dev-key
   JUDGE_MODEL=gpt-4.1-mini
   ```
6. Package skeleton + empty CI (ruff, mypy, pytest). Commit, create private remote, push.

**Gate:** `uv run evalgate --help` works; `uv run pytest` passes 0 tests; CI green.

---

## 3. Phase E1 — Domain design and eval-suite format (M0, 2–3 days)

This phase is design-heavy on purpose. The YAML contract is the product.

### Tasks
1. **Pydantic models** (`models/suite.py`, `models/case.py`), `extra="forbid"` everywhere:
   - `Suite`: `name`, `model{provider: 'openai-compatible'|'anthropic'|'mock', name,
     temperature=0, max_tokens=1024, base_url?}`, `prompt` (path), `cases_file` (path),
     `metrics: list[MetricSpec]` (discriminated union), `limits{max_cost_usd?,
     max_p95_latency_ms?}`, `regression{max_pass_rate_drop=0.03, min_cases=10}`,
     `judge{model?, rubric?}`.
   - `MetricSpec` variants: `exact_match{normalize: bool}`, `contains{value, mode:
     'any'|'all'}`, `json_schema_valid{schema}`, `regex{pattern}`,
     `llm_judge{rubric, threshold: 1..5}`, `latency_ms{max?}`, `cost_usd{max?}`.
   - `Case`: `id` (unique, stable), `input`, `expected?`, `context?`, `tags?`.
   - Paths resolve relative to the suite file; reject path traversal outside the repo root.
2. **Docs:** `docs/eval-suite-spec.md` with a full annotated example and a JSON Schema
   generated by `evalgate schema > schema.json`; commit both.
3. **Datasets (30–50 cases each, synthetic, no PII):**
   - `examples/support/datasets/support.jsonl` — 40 customer-support replies, each with
     `input` (ticket), `context` (policy snippets), `expected` (required facts/keywords).
     Hand-write or generate with a local script; document provenance. No copied support
     data.
   - `examples/classification/datasets/intents.jsonl` — 30 support intents with labels
     (`billing`, `bug`, `cancel`, `how-to`).
4. **Prompts and rubrics:**
   - `prompts/support.md`, `prompts/classify.md` with explicit output contracts.
   - `rubrics/helpfulness.md` and `rubrics/faithfulness.md`: 1–5 anchors, one paragraph per
     level, explicit failure at 1, explicit excellence at 5, instructions to ignore style.
5. **Schemas:** `schemas/reply.json` (answer + citations + confidence), used by
   `json_schema_valid`.
6. **Two example suites** wired end to end for later phases.
7. **ADR-001:** per-case pass/fail + aggregate, vs single average score. Decision: per-case
   required metrics + aggregate pass rate with interval; rationale: the per-case diff is
   what reviewers act on.
8. **CLI skeleton:** `evalgate validate <suite>`, `evalgate schema`; exit 2 on invalid.
9. **Tests:** valid suites parse; unknown keys rejected; missing prompt/dataset → clear
   error; duplicate case ids rejected; metric union rejects bad thresholds; path traversal
   rejected; schema command emits valid JSON Schema.

### Commits
```
feat(models): strict suite, case, and metric schemas
feat(cli): validate and schema commands
docs: eval suite specification with annotated example
data: synthetic support and classification datasets
docs(rubrics): helpfulness and faithfulness anchors
docs(adr): per-case pass/fail and aggregate semantics
test(models): validation and path-safety matrix
```

### Gate
`uv run evalgate validate examples/support/suite.yaml` exits 0; all invalid fixtures exit
2 with a readable message; `docs/eval-suite-spec.md` and schema agree (test asserts).

---

## 4. Phase E2 — Providers, metrics, runner, CLI (M1, 4 days)

### Tasks
1. **Provider protocol** (`providers/base.py`):
   ```python
   class Completion(BaseModel):
       text: str
       tokens_in: int; tokens_out: int
       cost_usd: Decimal
       latency_ms: int
       model: str; raw: dict | None = None

   class Provider(Protocol):
       async def complete(self, *, prompt: str, case: Case,
                          model: ModelSpec) -> Completion: ...
       async def aclose(self) -> None: ...
   ```
2. **OpenAI-compatible adapter:** `POST {base_url}/chat/completions`, `messages` with system
   + user rendered prompt, `temperature`, `max_tokens`, 60s timeout, retries on 429/5xx/
   timeout (max 4, exp backoff + jitter, honour `Retry-After`). Parse usage; compute cost
   from `providers/pricing.yaml` (per-model input/output USD per 1M tokens, `effective_date`);
   unknown model → cost 0 and a structured warning, never a crash.
3. **Anthropic adapter:** `POST /v1/messages`, `system` + `messages`, `max_tokens`, map
   usage fields, same retry policy.
4. **Mock + replay providers:** `MockProvider` returns deterministic text based on case id or
   a fixture map; `ReplayProvider` reads `tests/cassettes/*.json`. `--mock` selects the mock
   provider and must work with zero network and zero keys.
5. **Metrics registry** (`metrics/`): each metric gets `evaluate(case, completion, spec) ->
   MetricResult{metric, score: float 0..1, passed: bool, detail}`.
   - `exact_match`: exact or normalized (strip, lowercase, collapse whitespace) per config.
   - `contains`: `any`/`all`, case-insensitive.
   - `json_schema_valid`: parse JSON from the response (strip code fences), validate with
     `jsonschema`, detail lists the first error path.
   - `regex`: compiled once, `re.search`, invalid regex rejected at validation time.
   - `latency_ms`, `cost_usd`: compare against threshold or suite limits.
6. **Runner:** load cases, render prompt with Jinja2 (`{{ input }}`, `{{ context }}`),
   bounded concurrency (`--concurrency`, default 5, semaphore), per-case timeout, collect
   failures without aborting the run, compute per-case pass (all required metrics) and
   aggregates.
7. **CLI:**
   - `evalgate run <suite> [--mock] [--concurrency N] [--json out.json] [--html out.html]
     [--baseline <run-id|suite.json>] [--no-cache]`
   - Rich table: case id, per-metric pass, latency, cost; summary panel with pass rate,
     Wilson CI, total cost, p95 latency.
   - Exit codes: `0` pass, `1` gate fail (regression or hard limit), `2` config/usage error,
     `3` infrastructure error (provider unreachable after retries).
8. **Tests (no network):** respx adapter tests for 200, 429 then 200, 500 exhaustion,
   malformed JSON, missing usage; retry timing (seeded); cost math with a fixture pricing
   table; each metric unit-tested including invalid JSON and code fences; runner with 10
   mock cases, concurrency bound respected (track in-flight max), one failing case; exit
   codes 0/1/2/3; HTML/JSON snapshots stable.

### Commits
```
feat(providers): openai-compatible and anthropic adapters
feat(providers): pricing table, cost calculation, and retry policy
feat(providers): deterministic mock and replay providers
feat(metrics): exact, contains, json-schema, regex, latency, cost
feat(runner): bounded-concurrency engine and per-case pass logic
feat(cli): rich run output, json/html artifacts, exit codes
test(providers): retries, malformed responses, and cost math
test(runner): concurrency bound, failure isolation, exit codes
```

### Gate
`uv run evalgate run examples/support/suite.yaml --mock` produces a report and exit 0;
`--mock` run works with networking disabled; suite runs offline in CI.

---

## 5. Phase E3 — LLM judges, caching, calibration (M2, 4–5 days)

### Tasks
1. **Rubric prompt** (`judges/rubric.py`): system prompt states the role, anchors, and a
   strict JSON contract:
   ```json
   {"score": 1-5, "rationale": "<= 400 chars", "confidence": 0.0-1.0}
   ```
   Include the case input, context, expected facts (if any), and the candidate response.
   Forbid style bias explicitly.
2. **Parser** (`judges/parser.py`): extract JSON from raw text or code fences; validate
   types and ranges; on failure, one repair attempt appending the validation error; on
   second failure, record `judge_error` and treat the case as failed with a reason (do not
   crash the run). Handle refusals ("I cannot") as `score=1` with a documented flag.
3. **Normalization:** `(score - 1) / 4`; the raw score and rationale are stored; threshold
   is per-metric.
4. **Cache:**
   - Key = `sha256(response_text || rubric_hash || judge_model || prompt_version)`.
   - Store score, rationale, created_at, model, rubric hash.
   - Backends: Postgres (primary) and a local JSON/SQLite cache for keyless CLI use
     (`--cache-dir .evalgate-cache`). `--no-cache` bypasses reads and writes.
   - Report cache hit rate and saved cost in the summary.
5. **Calibration:** `evalgate calibrate --suite <s> --judges <a>,<b> --cases 30 [--mock]`
   runs two judges over the same responses, computes exact agreement, within-1 agreement,
   Cohen's kappa, and lists disagreements. Write `docs/calibration.md` with the numbers and
   an explicit "mock vs live" label.
6. **Tests:** fenced JSON, prose around JSON, out-of-range score, missing field, refusal,
   repair success, repair failure, cache hit/miss, rubric hash change invalidates cache,
   kappa math against a hand-computed fixture.

### Commits
```
feat(judges): anchored rubric prompt and strict json contract
feat(judges): robust parser with one repair attempt
feat(judges): content-addressed judge cache with postgres and local backends
feat(cli): calibrate command with agreement and kappa
docs: judge calibration report
test(judges): malformed output, refusal, repair, and cache invalidation
```

### Gate
Judge tests green with no network; calibration report committed with provenance; cache
demonstrably reduces judge calls on a second run (asserted in an integration test).

---

## 6. Phase E4 — Persistence, concurrency, baselines (M3, 3 days)

### Tasks
1. **Schema (Alembic 0001):** `suites`, `runs`, `results`, `judge_cache`,
   `run_metrics` (or compute aggregates), indexes on `runs(suite_id, started_at desc)`,
   `results(run_id)`, unique `results(run_id, case_id, metric)`, `judge_cache(hash)` unique.
   Use `status`: `queued|running|passed|failed|error`.
2. **Repository layer:** create run, record result (upsert for retries), finalize run,
   fetch baseline (latest `passed|failed` run for the same suite + git ref/commit, or an
   explicit run id), list runs.
3. **ARQ worker:** `run_suite` job with bounded concurrency, retries on provider 429,
   progress updates; API and CLI share the runner. Idempotency: same run id + case id +
   metric does not duplicate rows.
4. **Aggregates:** pass rate, Wilson 95% CI (hand-rolled, unit-tested), cost sum, p95
   latency (nearest-rank, documented), per-metric pass rates.
5. **Baseline + regression** (`runner/regression.py`): implement the rule from §1 with a
   truth table:
   - drop below threshold but overlapping CIs → **not** a regression;
   - drop beyond threshold with non-overlapping CIs → regression;
   - improvement, equal, small sample (`< min_cases`) → not a regression (documented);
   - hard-limit breach → fail independently.
6. **API (thin):** `POST /v1/runs` (suite path or inline YAML), `GET /v1/runs/{id}`,
   `GET /v1/runs/{id}/report.{json,html}`, `/healthz`, `/readyz`; `X-API-Key` auth.
   API is a convenience for the demo; the CLI remains primary.
7. **Tests:** Alembic up/down; repository CRUD; aggregation math with known fixtures;
   Wilson bounds (including 0 and n cases); regression truth table; concurrent worker
   writes without duplicate results; API auth and run lifecycle (Testcontainers).

### Commits
```
feat(storage): sqlalchemy models and alembic migration
feat(storage): run repository and baseline resolution
feat(worker): arq job for parallel suite execution
feat(runner): wilson interval, p95, and cost aggregation
feat(runner): regression rule with interval overlap
feat(api): run endpoints with api-key auth
test(runner): aggregation and regression truth table
test(storage): integration lifecycle with testcontainers
```

### Gate
Integration tests green against Postgres/Redis; regression truth table covers all six
cases; rerunning a finalized run does not duplicate rows.

---

## 7. Phase E5 — GitHub Action and PR reporting (M4, 3–4 days)

### Tasks
1. **`action.yml`** (composite): inputs `suite`, `baseline` (default `main`), `working-directory`,
   `fail-on-regression` (default true), `github-token`, `api-key`, `concurrency`,
   `comment` (default true). Steps: setup uv + Python, `uv tool install evalgate` (or
   install from the action path), run the suite with `--json`/`--html`, upload artifacts,
   post/update a PR comment.
2. **PR comment:** idempotent via marker `<!-- evalgate:report -->`; table with metric,
   baseline, current, delta, verdict; link to artifacts; list the top regressed cases (max
   10) with case id and metric. Use `gh api` with `GITHUB_TOKEN`; no third-party action
   needed. On fork PRs, tolerate a read-only token and skip the comment with a notice.
3. **Artifacts:** JSON (stable schema) and standalone HTML (Jinja2, inline CSS) with per-case
   diff, judge rationales for failures, cost/latency summary, and the regression
   explanation. Store under `reports/`.
4. **Example consumer repo** (`examples/consumer/`): workflow using the action against
   `examples/consumer/suite.yaml` with a mock provider step in CI (`--mock`) so the demo is
   reproducible without keys. Document the live variant.
5. **Flaky policy:** judge/provider errors retried once; if the retry changes the verdict,
   mark the run `flaky` and **do not fail** the gate by default, but print a warning and
   count it in the report. Document the rationale in `docs/failure-modes.md`.
6. **Tests:** action YAML lint (`actionlint`), PR-comment markdown snapshot, idempotent
   update marker, artifact contents, fail/pass exit propagation, a local simulation using
   `act` if Docker is available (optional), plus a unit test that runs the action's shell
   steps' commands.

### Commits
```
feat(action): composite github action with artifact upload
feat(report): pr comment table with regression details
feat(report): standalone html report
ci: actionlint and example consumer workflow
docs: flaky-run policy and ci integration guide
test(action): comment rendering and exit propagation
```

### Gate
`actionlint` green; comment snapshot stable; example consumer workflow runs end-to-end
locally (`act` optional) or via a documented dry-run script.

---

## 8. Phase E6 — Polish, demo, release (M5, 3 days)

### Tasks
1. **README:** pitch, badge, before/after PR screenshot, Mermaid architecture, suite example,
   measured cost per run (state model + case count + date), latency, cache hit rate,
   regression semantics, run instructions (`uvx evalgate` too), security notes, what's next.
2. **Demo:** `scripts/demo_regression.py` runs the suite with `--mock`, then with a weakened
   prompt variant; captures the pass-rate drop and exit code, writes both reports. Provide
   `scripts/demo.tape` for a GIF and mark the recording as a human step if needed.
3. **Case study** (`docs/case-study.md`): "how I decide an LLM feature is good enough to
   ship" — metric selection, anchors, sample size, cost, failure modes.
4. **Calibration doc:** numbers, method, and the mock/live label.
5. **ADRs:** 001 per-case semantics, 002 regression rule/interval overlap, 003
   no-framework adapters (why not LangChain), 004 judge caching key.
6. **Docker:** image that runs `evalgate` and the API; compose with postgres/redis for the
   API demo.
7. **Release:** tag `v1.0.0`, push, make public, topics (`llm`, `evals`, `ci`,
   `github-actions`, `python`), update parent `progress/log.md`. Marketplace publish is a
   human step; leave exact instructions.

### Commits
```
docs: readme with cost, latency, and cache numbers
docs: case study and judge calibration
docs(adr): regression rule, adapters, and cache key
build: docker image and compose for api
chore: release v1.0.0
```

---

## 9. Final walkthrough test

`scripts/walkthrough.ps1` — all offline (`--mock`); no API key required. Record output in
`docs/roadmap.md`.

| # | Action | Expected |
|---|---|---|
| 1 | `uv run evalgate validate examples/support/suite.yaml` | exit 0 |
| 2 | `uv run evalgate run ... --mock --json r1.json --html r1.html` | exit 0; pass rate printed; artifacts exist |
| 3 | Run again; assert cache hit rate | judge calls on second run = 0 for cached cases |
| 4 | `uv run evalgate run ... --mock --prompt-variant weakened` | exit 1; per-case diffs list the regressed cases; PR-comment markdown generated |
| 5 | Lower `max_cost_usd` below actual | exit 1 with a hard-limit message (not a regression message) |
| 6 | `uv run evalgate calibrate --mock` | agreement + kappa rendered; report written |
| 7 | Start compose; `POST /v1/runs`; poll `GET /v1/runs/{id}` | status `passed`; results persisted |
| 8 | Repeat POST with the same API key and unauth request | first 201, unauth 401 |
| 9 | `actionlint action.yml` | exit 0 |
| 10 | Render PR comment for run 4 | table includes baseline, current, delta, verdict; marker present |
| 11 | Break a judge fixture (malformed JSON) and rerun tests | repair path or graceful `judge_error`, no crash |
| 12 | Network-disabled pytest (`respx` + vcr `record_mode=none`) | all tests pass, zero live calls |
| 13 | `docker build .` | succeeds; `docker run ... evalgate --help` works |

Also fresh-clone: clone to `%TEMP%\evalgate-smoke`, `uv sync`, run steps 1, 2, 4, 12.

---

## 10. Definition of Done checklist

- [ ] README pitch + Mermaid + measured cost/latency/cache numbers + run steps + tradeoffs
- [ ] `evalgate run` works offline with `--mock`; exit codes are correct
- [ ] CI green: ruff, mypy strict, pytest, docker build; **no network in tests**
- [ ] Failure tests: 429/5xx/timeout, malformed judge JSON, out-of-range score, refusal,
      cache invalidation, hard-limit breach, small-sample regression, auth rejection
- [ ] `/healthz`, `/readyz`, structured logs with request ids (API)
- [ ] OpenAPI spec for the API
- [ ] 3–4 ADRs + case study + calibration + failure modes + security notes
- [ ] GitHub Action with idempotent PR comment and artifacts
- [ ] HTML + JSON reports checked in as examples
- [ ] MIT license, conventional history, `v1.0.0`
- [ ] Demo GIF or live run; cost per run stated with model and date
- [ ] `docs/interview-notes.md`: precision/recall reasoning, sample-size argument, judge
      failure modes

---

## 11. Risks and fallbacks

| Risk | Mitigation |
|---|---|
| No LLM API key | `--mock` is the default demo; every test is offline; live numbers are clearly labelled and optional |
| Judge scores feel arbitrary | Anchored rubrics, calibration with a second judge, kappa/agreement reported, per-case rationale stored |
| Regression gate false positives | Wilson intervals + `min_cases` + documented flaky policy; truth-table tests |
| Prompt drift breaking fixtures | Prompt version included in cache key; fixtures pinned per suite; regenerate deliberately |
| Cost accounting wrong | Pricing table with `effective_date`; unknown model warns and reports 0; unit tests per provider |
| Action token permissions on fork PRs | Detect read-only token and skip the comment; artifacts + exit code still work |
| Postgres adds deployment friction | CLI works with the local cache and no DB; DB required only for the API/worker demo |
| Scope creep (web UI, agent tracing) | Explicitly out; linked as alternatives in tradeoffs |
