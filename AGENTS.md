# Agent Instructions — EvalGate

This repository is already bootstrapped: directory, git repo on `main`, MIT license, and a
private GitHub remote exist. **Do not run `git init`, create a new repo, or replace the
remote.** Start with the tooling part of Phase E0 in [`docs/plan.md`](docs/plan.md).

## Read first

1. [`docs/spec.md`](docs/spec.md) — product scope, suite format, milestones.
2. [`docs/plan.md`](docs/plan.md) — the authoritative execution plan.
3. [`docs/master-plan.md`](docs/master-plan.md) — commit, phase, and release conventions.
4. [`docs/roadmap.md`](docs/roadmap.md) — update this at every gate.

## How to work

- Follow the phases in order: E0 tooling → E1 domain design → E2 providers/metrics/runner →
  E3 judges/cache/calibration → E4 persistence/baselines → E5 GitHub Action → E6 release.
- Work each phase on `phase/<n>-<name>`, commit every meaningful change with Conventional
  Commits, run the full gate, merge to `main` with `--no-ff`, tag the phase, and push.
- `scripts/verify.ps1` must pass before a phase is considered done: format, lint, strict mypy,
  tests, coverage.
- **No network in the test suite.** Use `respx`, recorded fixtures, and the deterministic mock
  provider. Live provider calls are optional demo steps only.
- Never weaken a failing test to make a phase pass. Fix the code or cut scope explicitly.
- Do not build a web UI. The CLI, reports, and the GitHub Action are the product.

## Environment notes (this machine)

- Python 3.12 and `uv` are installed. Use `uv add` / `uv run`; do not create a venv by hand.
- Docker Desktop must be running with Linux containers. If it is not, stop and report.
- `gh` is authenticated as `supremeyuma`.
- Provider API keys are optional and must never be committed. Default every test and demo to
  `--mock`.

## Parallel build coordination

Two other agents are building `statusbeam` and `edgelink` on the same machine, and HookRelay
may be running. Use these host ports so stacks do not collide:

| Service | Port |
|---|---|
| Postgres (host) | **5434** |
| Redis (host) | **6381** |
| API | **8001** |

- Put `name: evalgate` in the compose file and use these host mappings from the start.
- Set `DATABASE_URL` / `REDIS_URL` in `.env.example` and `.env` to the reserved ports.
- CI services stay on 5432/6379 inside the runner; only local host mappings change.
- Do not publish Postgres/Redis ports in production compose.
- Do not touch `C:\Users\Supreme\repos\hookrelay`, `statusbeam`, or `edgelink`.

## Human-only checkpoints

Stop and report rather than faking: GitHub auth loss, Docker unavailable, a live provider key
for a demo, an Action Marketplace listing, or a VPS. Everything else should be resolved
autonomously using the plan's documented fallbacks.

## Definition of done

The release gate in `docs/master-plan.md` §7 plus the project checklist in
`docs/plan.md` §10: offline test suite, green CI, Action and reports, walkthrough, `v1.0.0`
tagged and pushed, repo public with topics, and the parent
`ai-engineering-pivot/progress/log.md` updated.
