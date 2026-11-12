# ADR-002: Regression rule with Wilson intervals

**Status:** accepted · **Phases:** E2 (implemented), E4 (persisted baselines)

## Context

A gate that fails on every small drop is ignored; a gate that only fails on large drops misses
slow degradation. Eval suites are usually small (10–100 cases), so sampling noise dominates: a
2-point drop on 40 cases is one case, and a 10-point drop on 20 cases may still be two cases
moving.

We need a rule that is explainable to a reviewer, cheap to compute, and conservative in the
direction of not blocking good PRs.

## Decision

A drop is a regression only when **all** of the following hold:

1. `current_total >= min_cases` and `baseline_total >= min_cases`.
2. `baseline_pass_rate - current_pass_rate > max_pass_rate_drop`.
3. The Wilson 95% intervals do not overlap: `current_high < baseline_low`.

The Wilson score interval for `k` successes out of `n` at `z = 1.96`:

```
denominator = 1 + z²/n
center      = (p + z²/(2n)) / denominator
margin      = z * sqrt(p(1-p)/n + z²/(4n²)) / denominator
interval    = (center - margin, center + margin)
```

The interval is computed from the same pass counts that produce the pass rate, so there is no
extra state to persist beyond `n`, `k` (equivalently pass rate), and the two bounds.

Hard limits are separate: breaching `max_cost_usd` or `max_p95_latency_ms` fails the run even
when the pass rate is unchanged.

## Consequences

- Small suites can show large-looking drops without failing; the report explains why.
- A real regression larger than the noise band fails reliably once `n` is adequate.
- Adding cases narrows the interval, making the gate more sensitive — a deliberate trade.
- The rule is direction-aware: improvements and equal pass rates never fail.
- The `min_cases` guard prevents a 3-case suite from producing a "significant" drop.

## Truth table (all covered by tests)

| Baseline | Current | `max_drop` | Intervals | Result |
|---|---|---|---|---|
| 90% (100 cases) | 88% | 0.03 | overlap | not a regression |
| 90% (100) | 87% | 0.03 | overlap | not a regression (exactly at threshold) |
| 90% (100) | 80% | 0.03 | overlap | not a regression (noise) |
| 90% (100) | 60% | 0.03 | separated | **regression** |
| 90% (100) | 95% | 0.03 | separated | not a regression (improved) |
| 100% (5 cases) | 0% | 0.03 | separated | not a regression (small sample) |

## Alternatives considered

- **Raw threshold only:** ignores sample size; fails on one case at n=20.
- **Fixed confidence with a normal approximation:** poor at rates near 0 or 1, which is exactly
  where eval suites live. Wilson behaves at the boundaries.
- **Bootstrapping:** more general but slower, stochastic, and harder to explain in a comment.
- **Sequential tests:** better for continuous monitoring, overkill for one comparison per PR.
- **Paired per-case tests:** promising for large suites, but the metric mix (continuous judge
  scores and binary schema checks) makes a single paired test awkward. Left as future work.
