# EvalGate

> A regression-testing system for LLM features: define an eval suite in YAML, run it against
> any provider, fail the pull request when quality drops below threshold.

**Status:** in development (Phase E1). The execution plan and phase evidence live in
[`docs/roadmap.md`](docs/roadmap.md).

**Stack:** Python 3.12 · uv · FastAPI · Pydantic v2 · SQLAlchemy 2.0 · PostgreSQL 16 · Redis 7 ·
ARQ · httpx · pytest · Docker · GitHub Actions

## Start here

1. [`AGENTS.md`](AGENTS.md) — build contract, parallel port reservations, and first steps.
2. [`docs/spec.md`](docs/spec.md) — the product spec and milestones.
3. [`docs/plan.md`](docs/plan.md) — phase-by-phase execution plan with gates and tests.
4. [`docs/master-plan.md`](docs/master-plan.md) — shared conventions and release gate.
5. [`docs/roadmap.md`](docs/roadmap.md) — phase checkboxes and evidence.

The repository bootstrap (folder, git, license, remote) is already done. Begin with the
Phase 0 tooling tasks in `docs/plan.md`, then Phase E1.

## License

MIT
