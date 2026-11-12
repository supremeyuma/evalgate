# ADR-001: Per-case pass/fail with an aggregate pass rate

**Status:** accepted · **Phase:** E1

## Context

An eval run produces one response per case and several metric verdicts per response. There
are two plausible ways to summarize quality:

1. A single average score across all metrics and cases (for example mean judge score).
2. A pass/fail verdict per case, then an aggregate pass rate.

The product exists to gate pull requests. A reviewer needs to know *which behavior broke*,
not only that a mean moved by 0.04.

## Decision

- Each metric returns `score` in `[0, 1]`, `passed`, and a human-readable `detail`.
- A case passes only if **every** configured metric passes. Metrics are requirements, not
  weighted votes.
- The suite pass rate is `passed_cases / total_cases`.
- The regression gate compares pass rates with a Wilson 95% interval (ADR-002), not with a
  raw difference alone.
- Reports always include a per-case diff against the baseline. The aggregate is a summary,
  never the only output.

## Consequences

- One hard metric (for example schema validity) can dominate the pass rate. That is
  intentional: an invalid JSON reply is not "mostly fine" for a machine consumer.
- Partial credit lives inside metrics (judge score, similarity), not across metrics.
- Adding a metric can lower the pass rate without changing responses. Treat metric changes
  as suite-version changes and re-baseline deliberately.
- Reviewers get an actionable diff: `case id → failing metric → detail`.

## Alternatives considered

- **Mean score only:** loses per-case actionability and hides bimodal failures.
- **Weighted metric composite:** weights are arbitrary and drift; hard requirements are
  easier to explain to a reviewer.
- **Majority of metrics:** lets a broken schema pass because two soft metrics succeeded.
