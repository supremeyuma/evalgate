# EvalGate Roadmap and Gate Evidence

Source plan: `docs/plan.md`. Update this file at every phase gate. A checked box means
verified, not "written".

## E0 — Bootstrap

- [x] Folder created at `../evalgate`
- [x] Git repository on `main`, `core.autocrlf=false`
- [x] MIT license, `.gitignore`, `.gitattributes`, `.editorconfig`
- [x] Execution plan, spec, master plan, and agent instructions committed
- [x] Private GitHub remote created and pushed
- [x] Tooling: `uv init` with Python 3.12, runtime/dev dependencies, package layout, CLI
      entry point, Ruff/mypy strict/pytest config
- [x] Empty `uv run pytest` and `uv run evalgate --help` green

**Evidence:** `uv 0.13.7`, Python 3.12.16. `uv run evalgate --version` → `evalgate 0.1.0`.
`uv run pytest` → 3 passed; coverage 83%. `scripts/verify.ps1` → ALL CHECKS PASSED.
Reserved host ports (5434 Postgres, 6381 Redis, 8001 API) are set in `.env.example`.
Repository: <https://github.com/supremeyuma/evalgate>.

## E1 — Domain design and suite format (M0)

- [ ] Strict Pydantic suite/case/metric models, YAML examples, JSON Schema
- [ ] 30–50 synthetic cases, two rubrics with anchors
- [ ] ADR-001 per-case vs aggregate
- [ ] `evalgate validate` and `evalgate schema`

**Gate evidence:** _pending_

## E2 — Providers, metrics, runner, CLI (M1)

- [ ] OpenAI-compatible + Anthropic adapters with retry/timeout
- [ ] Mock/replay providers; deterministic metrics
- [ ] Bounded-concurrency runner, rich table, exit codes 0/1/2/3
- [ ] No-network tests

**Gate evidence:** _pending_

## E3 — LLM judges, caching, calibration (M2)

- [ ] Anchored rubric prompt + strict JSON contract + repair attempt
- [ ] Content-addressed judge cache (Postgres + local)
- [ ] Two-judge calibration with agreement/kappa
- [ ] Failure-path tests

**Gate evidence:** _pending_

## E4 — Persistence, concurrency, baselines (M3)

- [ ] SQLAlchemy + Alembic schema, ARQ worker
- [ ] Wilson interval, p95, cost aggregation
- [ ] Regression rule with interval overlap + truth-table tests
- [ ] Thin API with API-key auth

**Gate evidence:** _pending_

## E5 — GitHub Action and PR reporting (M4)

- [ ] Composite action, artifacts, idempotent PR comment
- [ ] Example consumer workflow
- [ ] Flaky-run policy documented

**Gate evidence:** _pending_

## E6 — Polish, demo, release (M5)

- [ ] README with cost/latency/cache numbers, case study, calibration
- [ ] Demo regression script, ADRs 001–004
- [ ] `v1.0.0`, public repo, topics, parent log updated

**Gate evidence:** _pending_
