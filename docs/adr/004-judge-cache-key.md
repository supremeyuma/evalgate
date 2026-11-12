# ADR-004: Judge cache key

**Status:** accepted · **Phase:** E3

## Context

Judging every response on every run is the dominant cost of an eval suite. Re-running the
same suite against an unchanged prompt should not pay for the same judgments twice. At the
same time, a stale judgment is worse than no cache: it can hide a regression.

## Decision

The cache key is:

```
sha256(response_text || 0x1f || sha256(rubric_text) || 0x1f || judge_model || 0x1f || prompt_version)
```

- **response_text** — a changed model output must be re-judged.
- **rubric hash** — editing anchors changes the meaning of a score.
- **judge model** — two judges are not interchangeable.
- **prompt version** — a constant in `evalgate.constants`, bumped whenever the judge prompt
  contract changes (for example, when the JSON contract or anchoring instructions change).
- The **threshold is not in the key**: the cache stores the raw 1–5 score, and the current
  threshold is applied on read. Changing a threshold does not require new judge calls.

Entries store the score, rationale, confidence, judge model, rubric hash, response hash,
and the cost of the call that produced them. On a hit, the stored cost is reported as saved
cost. The response text itself is never stored, only its hash.

Backends:

- **SQLite** (`--cache-dir`, default `.evalgate-cache/judge_cache.sqlite3`) for keyless CLI
  use and offline demos.
- **Postgres** (`judge_cache` table) for the API and worker; the CLI can opt in with
  `JUDGE_CACHE_BACKEND=postgres`.
- `--no-cache` uses a null backend that neither reads nor writes.

There is no TTL. Invalidate deliberately by changing the rubric, the prompt version, or the
judge model. This keeps offline runs reproducible.

## Consequences

- Identical responses within one run share a judgment; the report counts those as hits.
- Cache hits are cheap but not free: the cache lookup still happens per metric.
- A judge prompt change without a version bump can serve stale scores. The version constant
  lives next to the prompt and is part of review.
- Rationales are stored; they must not contain secrets. Judges are instructed not to echo
  credentials, and the suite's own inputs are already repo content.
