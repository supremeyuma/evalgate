# Execution Master Plan — Four Artifact Repos

**Status:** ready for autonomous coding agents
**Source of truth:** `README.md`, `PLAN.md`, `projects/00-project-rubric.md`, and the four
project specs in `projects/`
**Outcome:** four sibling repositories, built **one at a time**, each shipped to `v1.0.0`
with green CI, tests, a reproducible walkthrough, and pushed commits.

---

## 1. What gets built, in what order

| Order | Repo | Plan file | Spec | Working days (agent) | Hard external dependencies |
|---|---|---|---|---|---|
| 1 | `hookrelay` | `execution/01-hookrelay-plan.md` | `projects/p1-hookrelay.md` | 18–22 | Docker, GitHub |
| 2 | `statusbeam` | `execution/02-statusbeam-plan.md` | `projects/t1-statusbeam.md` | 20–24 | Docker, GitHub, Playwright browsers |
| 3 | `evalgate` | `execution/03-evalgate-plan.md` | `projects/p2-evalgate.md` | 16–20 | Docker, GitHub, optional LLM API key |
| 4 | `edgelink` (stretch) | `execution/04-edgelink-plan.md` | `projects/t2-edgelink.md` | 10–12 | Cloudflare account (optional), Docker for `act` only |

**Order is mandatory.** Do not work on two repos in the same day. Do not start repo N+1
until repo N has passed its release gate (§7).

Why this order:
1. HookRelay establishes Python, async, Postgres/Redis, testing, CI, and reliability
   patterns that EvalGate reuses.
2. StatusBeam proves TypeScript backend depth and is the highest-volume keyword pair.
3. EvalGate is the flagship and benefits from the Python foundations; it is treated as the
   last *required* artifact.
4. EdgeLink is an explicit stretch. **Start it only if EvalGate is tagged `v1.0.0` and at
   least 10 working days remain in the budget.** If not, record it as deferred in
   `progress/log.md` and stop.

---

## 2. Where the repos live

Each plan's **Phase 0** creates the repo at `../<name>` relative to this planning repo,
which resolves to:

```
C:\Users\Supreme\repos\
  ai-engineering-pivot\   <- this repo (plans live here)
  hookrelay\
  statusbeam\
  evalgate\
  edgelink\                <- only if the stretch is approved
```

Canonical bootstrap block (each project plan repeats it with its own name):

```powershell
$name = "hookrelay"
$dest = Join-Path (Split-Path -Parent (Get-Location)) $name   # ../hookrelay
New-Item -ItemType Directory -Path $dest -Force
Set-Location $dest
git init -b main
git config core.autocrlf false
```

One repo = one git repository. Do **not** make them a monorepo. Do **not** add them as
submodules of `ai-engineering-pivot`.

---

## 3. Global prerequisites

Run once, before Heartbeat 1 of HookRelay. Every command is PowerShell on Windows 11.

```powershell
winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements
winget install --id GitHub.cli -e
winget install --id astral-sh.uv -e
winget install --id OpenJS.NodeJS.LTS -e
winget install --id Docker.DockerDesktop -e
winget install --id k6.k6 -e
corepack enable
corepack prepare pnpm@9.15.0 --activate
```

If a `winget` ID is unavailable, use `winget search <name>`, then the vendor installer. Do
not substitute a different runtime version silently.

Verification (all must pass before any project starts):

```powershell
git --version          # any modern git
gh --version
gh auth status         # must show a logged-in account
uv --version
node --version         # v22.x (>=22 accepted; record actual)
pnpm --version         # 9.x
docker version         # client + server; Docker Desktop must be running
docker compose version
k6 version
```

**Hard prerequisite:** Docker Desktop must run Linux containers with the WSL2 backend.
HookRelay, StatusBeam, and EvalGate integration tests use Testcontainers and/or compose.
If Docker is unavailable, stop and report the blocker; do not replace Postgres/Redis with
SQLite to "keep moving" (EvalGate unit tests may use SQLite only where its plan allows).

### Human-only checkpoints

These are the only steps an agent must not fake. Batch them before starting.

| Checkpoint | Needed by | Fallback if unavailable |
|---|---|---|
| `gh auth login` with `repo` + `workflow` scopes | Phase 0 of every repo | Local commits; record blocker; do not invent a remote |
| Docker Desktop running | HookRelay Phase 1 | Stop; fix Docker |
| Cloudflare account + API token; **Workers Paid** for Queues | EdgeLink only | Local Miniflare build; mark deploy gate deferred in README |
| LLM provider API key (OpenAI-compatible or Anthropic) | EvalGate live demo only | Ship with `--mock`; label all demo numbers as mock; never commit keys |
| VPS / Fly.io account for live demo URL | Release phase | Local demo GIF via `vhs`; mark live URL deferred |
| Demo video recording / Marketplace listing publish | Release phase | Provide a scripted `.tape`/`scripts/demo.*`; leave the upload as a 1-step human task |

---

## 4. Operating conventions (all repos)

### Branches
- `main` is always green.
- Work each phase on `phase/N-short-name` (e.g. `phase/2-ingest-idempotency`).
- At a phase gate, merge to `main` with `--no-ff` so the phase boundary is visible:
  ```powershell
  git switch main
  git merge --no-ff phase/2-ingest-idempotency -m "merge: phase 2 - ingest and idempotency"
  git tag -a v0.2.0 -m "Phase 2: ingest, HMAC, idempotency"
  git push origin main --tags
  ```
- Never force-push `main`. Never rewrite commits that are already pushed.

### Commits
- Conventional Commits: `feat(api): ...`, `fix(worker): ...`, `test(ingest): ...`,
  `docs(adr): ...`, `ci: ...`, `chore: ...`, `refactor: ...`, `perf: ...`.
- **Commit on every meaningful change**: one logical change + its tests + any doc update.
  A commit must build and pass the phase's fast checks on its own.
- Keep commits under ~400 changed lines where practical. Do not commit commented-out code,
  `.env` files, secrets, or generated build output.
- Squash local WIP before a gate with `git rebase -i` **only** on unpushed commits.
- End every commit message body with the verification performed, e.g.
  `Verified: uv run pytest tests/unit -q (42 passed)`.

### Phase protocol (apply to every phase in every repo)
1. **Initiate** — create the branch; tick the phase's `docs/roadmap.md` section; re-read the
   matching spec section; list the acceptance tests before writing code.
2. **Build** — implement in small commits; write the hard-path test immediately after (or
   before) the code it covers.
3. **Test** — run the full gate: format check, lint, typecheck, unit + integration tests,
   coverage on core modules, plus the phase's special check.
4. **Record** — write measured numbers/decisions into `docs/roadmap.md` and, where relevant,
   an ADR. No unverifiable claims.
5. **Push** — merge to `main`, tag the phase, push commits and tags.

### Test bar
- Core business modules: **≥80% line coverage**; do not chase 100%.
- Every phase gate runs the **entire** suite, not just new tests.
- Failure paths are mandatory: timeout, retry, malformed input, auth rejection, duplicate
  request, dependency down.
- Integration tests use real Postgres/Redis (compose or Testcontainers). Mocking the
  database is not an integration test.
- No test may call the public internet. EvalGate uses recorded fixtures/mocks; StatusBeam
  and HookRelay use local fake servers.
- A flaky test is a bug: fix it or delete it. Do not add retries to hide flakes (load-test
  scripts may retry).

### CI requirements (every repo)
- `.github/workflows/ci.yml` on `push` + `pull_request` to `main`.
- Steps: dependency install (cached) → format check → lint → typecheck → tests with
  coverage → production Docker build (where applicable).
- Services: `postgres:16-alpine`, `redis:7-alpine` with health checks.
- Badge at the top of the README.
- No CI job may require a secret to pass. Live-provider and deploy jobs are separate,
  conditional (`if: secrets.X != ''`), and never required for the green badge.

### Documentation requirements (every repo)
- `README.md` from `templates/repo-readme-template.md`: pitch, Mermaid architecture,
  measured results, run instructions, design decisions, security notes, what's next.
- `docs/adr/NNN-title.md` from `templates/adr-template.md`; 3 ADRs minimum.
- `docs/roadmap.md`: the phase checklist with gate evidence (commands + outputs/numbers).
- `LICENSE` MIT, `.gitignore`, `.gitattributes` (`* text=auto eol=lf`), `.env.example`.

---

## 5. Phase-gate verification script (pattern)

Each repo must contain `scripts/verify.ps1` (and a CI equivalent) that fails on the first
error and prints a summary. Minimum content:

```powershell
$ErrorActionPreference = "Stop"
Write-Host "== format ==";   <formatter check>
Write-Host "== lint ==";     <linter>
Write-Host "== typecheck ==";<typechecker>
Write-Host "== tests ==";    <test command with coverage>
Write-Host "== build ==";    <docker build or package build>
Write-Host "ALL CHECKS PASSED"
```

A phase is **not** done because the code "looks right". It is done when `scripts/verify.ps1`
exits 0 **and** the phase-specific acceptance checks in the project plan pass.

---

## 6. Definition of Done (maps the rubric to evidence)

Every repo's `docs/roadmap.md` must end with this table filled in with file paths/URLs:

| Rubric item | Evidence artifact |
|---|---|
| One-sentence pitch | `README.md` first blockquote |
| Architecture diagram + 3–5 tradeoffs | `README.md` Mermaid + Design decisions section |
| `docker compose up` works | `README.md` Run it; verified from a clean clone |
| CI lint/typecheck/tests + badge | `.github/workflows/ci.yml`, badge URL, last green run |
| Failure-path tests | `tests/` names listed in `docs/roadmap.md` |
| OpenAPI/typed client | `/openapi.json` + checked-in spec or generated client |
| Structured logs + `/healthz` + `/readyz` | code paths + sample log line in README |
| Docs page/post explaining *why* | `docs/case-study.md` |
| License | `LICENSE` |
| Conventional commits, clean history | `git log --oneline` |
| Load-test numbers | `load/results/*` + README table with hardware |
| Failure-mode section | `docs/failure-modes.md` |
| 3 ADRs | `docs/adr/001..003` |
| Observability | OTel trace screenshot/output + metrics list |
| Security notes | README Security notes + `docs/security.md` |
| Cost note | README cost table (per 1k/10k/100k units) |
| Demo | live URL or `docs/demo.gif` |
| Interview readiness | `docs/interview-notes.md` (data model sketch, 3 failure modes) |

---

## 7. Release gate (must pass before the next repo starts)

For repo N:
- [ ] `scripts/verify.ps1` exits 0 from a **fresh clone** (`git clone` into a temp dir).
- [ ] `docker compose up --build` reaches healthy state in <5 minutes; README run steps
      are exact, including required env vars.
- [ ] Final walkthrough in the project plan has been executed end-to-end and its observed
      output recorded in `docs/roadmap.md`.
- [ ] CI green on `main` for the release commit.
- [ ] `v1.0.0` annotated tag exists and is pushed.
- [ ] Repo is public, `LICENSE` visible, topics set, description set, README badge renders.
- [ ] No secrets in history: `git log -p | Select-String -Pattern "sk-|api_key|secret"` and
      `gitleaks detect` (install once) are clean.
- [ ] `ai-engineering-pivot/progress/log.md` updated with shipped scope, numbers, and the
      deferred list.

Only then open the next project plan.

---

## 8. Failure and fallback policy (agent autonomy)

The goal is minimal human intervention. Resolve ambiguity yourself using these rules:

1. **Spec conflict:** the project spec wins over this master plan; the rubric wins over
   both. Record the deviation in the repo's `docs/roadmap.md` and an ADR if structural.
2. **Missing optional tool/service:** use the fallback in §3 and label the result honestly.
3. **Blocked >30 minutes on an environment issue:** try one documented alternative, then
   stop that phase, commit the work in a green state, and report the exact blocker.
   Do not disable tests or CI to proceed.
4. **Load target unreachable on the host:** publish the *actual reproducible* number and
   the bottleneck. Never publish a number you cannot reproduce.
5. **LLM/API quota:** switch to the mock/recorded provider. Mark any derived calibration or
   cost numbers as mock-derived.
6. **Do not expand scope.** Features listed under "Out" or "Stretch" stay out unless the
   project plan explicitly schedules them.
7. **No new technology mid-phase** (PLAN.md anti-failure rule 1). Write it in "what I'd do
   next" instead.

---

## 9. Final portfolio wrap (after EdgeLink or its deferral)

Do this once, not per repo:

- [ ] Pin the four (or three) repos on GitHub; same description prefix
      `Applied AI/Backend · <one-line>`.
- [ ] One-page portfolio linking live demos and case studies.
- [ ] CV variants updated (`ai-backend`, `business-systems`) with repo links and one
      measured number per project.
- [ ] Four 60–90s demo recordings (or GIFs) linked at the top of each README.
- [ ] `progress/log.md` final entry: shipped, deferred, OSS status, next 30 days.
- [ ] Apply to 20 roles before starting any fifth project.

---

## 10. Plan index

1. `execution/01-hookrelay-plan.md` — Python/FastAPI reliability gateway
2. `execution/02-statusbeam-plan.md` — TypeScript/NestJS uptime monitoring
3. `execution/03-evalgate-plan.md` — Applied AI eval CI gate
4. `execution/04-edgelink-plan.md` — Cloudflare Workers link shortener (stretch)
