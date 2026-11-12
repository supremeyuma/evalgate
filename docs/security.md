# Security notes

## Assets

- Provider API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`).
- The API key for the demo API (`EVALGATE_API_KEY`, default `dev-key`).
- Suite inputs and model outputs, which may contain customer text.
- The database (runs, results, judge rationales).

## Trust boundaries

1. **Suite author → runner.** A suite is code-like: it names files and templates prompts.
2. **Runner → provider.** Prompts and case data leave the machine when a live provider is used.
3. **CI → GitHub.** The Action reads a baseline ref and writes a PR comment.
4. **Client → API.** Authenticated by `X-API-Key`.

## Mitigations

### Path safety

- Every suite asset resolves relative to the suite file and must stay inside the project root
  (nearest `.git` ancestor, or the suite directory outside a repo).
- Absolute paths are rejected; symlinks are resolved before the check, so they cannot escape.
- JSONL datasets are parsed line by line; malformed rows fail with a line number.

### Secrets

- Keys are read from the environment (or `.env`, which is gitignored) and never embedded in
  reports, logs, judge output, or the cache.
- The pricing table and provider requests contain no credentials.
- Example suites default to the mock provider; CI requires no secret to pass.
- `.env.example` contains empty key placeholders only.

### Judge cache

- Keyed by SHA-256 over response text, rubric hash, judge model, and judge prompt version.
- Stores the response **hash**, not the response. Stores score, rationale, confidence, model,
  and cost.
- A read-only SQLite file for the CLI; Postgres for the API/worker.

### API

- `X-API-Key` is compared with `secrets.compare_digest`; missing or wrong keys get 401.
- `POST /v1/runs` accepts a server-side suite path or inline YAML. Inline YAML is written next
  to the caller-supplied working directory, executed, and deleted in a `finally` block.
  **Do not expose the API to untrusted users**: a caller who can write files can run arbitrary
  suites. It is a demo/worker interface, not a multi-tenant service.
- `/healthz` and `/readyz` are unauthenticated by design (liveness/readiness only).
- Request logs include method, path, status, duration, and a request id — not headers or bodies.

### Reports

- HTML is rendered with Jinja2 autoescaping enabled; model output is escaped.
- The PR comment is ASCII-only, limited to 100 comments per lookup, and marker-scoped so it
  cannot overwrite unrelated comments.
- The comment excludes full responses; it shows case ids, metric names, and truncated details.

### CI

- The Action uses the job's `GITHUB_TOKEN`; fork PRs get a read-only token and the comment step
  degrades to a notice.
- `actions/checkout` is the only third-party action besides `setup-uv`, `upload-artifact`,
  and `actionlint`; versions are pinned to major tags and reviewed on upgrade.
- No workflow requires a secret to be green.

## Known limitations

- Prompt injection through `case.context` can influence a live model. Judge caching and
  deterministic metrics reduce blast radius but do not eliminate it; do not put secrets in
  context.
- The SQLite cache is not encrypted at rest; it contains rationales, not raw responses.
- The API has no rate limiting or per-tenant isolation. Put it behind a network boundary.
- `--prompt-variant weakened` is a demo feature; do not use it as a production kill switch.

## Reporting

Open an issue with reproduction steps; do not include keys or customer text. Rotate any key
that may have been exposed.
