# Case study: how I decide an LLM feature is good enough to ship

This is the reasoning behind EvalGate's defaults, written as if for a team adopting it. The
short version: quality is a set of per-case requirements, the gate compares distributions
rather than point estimates, and every threshold has a named owner.

## 1. Start from the failure you cannot ship

For a support-reply feature, the unacceptable failures are concrete:

- the reply is not valid JSON, so the downstream UI breaks;
- the reply invents a refund window or a price;
- the reply asks for a password or full card number;
- the reply takes longer than the UI budget or costs more than the ticket is worth.

That list becomes metrics, not a vibe. `json_schema_valid`, a faithfulness rubric, a
prohibited-content check (a regex in the example), `latency_ms`, and `cost_usd`. Each is a
hard requirement for a case to pass.

**Decision:** do not average these. A response that is cheap, fast, and beautifully written
but invalid JSON is a failure.

## 2. Choose metrics by what a reviewer can act on

| Question | Metric | Why not a judge |
|---|---|---|
| Is the contract satisfied? | `json_schema_valid` | Deterministic, free, and unambiguous. |
| Are required facts present? | `contains` / `exact_match` | Cheap and stable for classification and keyword requirements. |
| Is the answer grounded and helpful? | `llm_judge` with anchors | The only practical way to grade free-form quality. |
| Is it fast/cheap enough? | `latency_ms`, `cost_usd` | Hard budgets, measured per case. |

A judge is the most expensive and least reliable metric, so it is used only where a
deterministic check cannot express the requirement.

## 3. Write anchors before writing prompts

The helpfulness rubric has one paragraph per score. Score 5 is "answers the exact question,
states the applicable policy, gives a next action"; score 1 is "does not answer, contradicts
policy, invents policy, or asks for credentials". Without anchors, two runs of the same judge
disagree with each other and the gate measures noise.

**Decision:** a `llm_judge` metric cannot be configured without a rubric, and a rubric change
invalidates the cache (ADR-004). Rubrics are versioned by content, not by hope.

## 4. Calibrate the judge, then trust it only for the delta

The committed calibration is mock-derived on purpose: it proves the plumbing (two judges, one
generation pass, agreement, kappa, disagreements) without pretending to measure a real judge.
A live calibration is one command:

```powershell
uv run evalgate calibrate --suite examples/support/suite.yaml --judges gpt-4.1-mini,gpt-4.1 --cases 30
```

Read it as: exact agreement, within-1 agreement, and Cohen's kappa. If kappa is near zero, the
judge is not a measurement instrument yet; fix anchors or the rubric before gating on it.

## 5. Size the sample before trusting a delta

A 40-case suite has a Wilson 95% interval of roughly 91–100% at a perfect score. One flipped
case moves the point estimate by 2.5 points; the interval barely moves. That is why the
regression rule requires both a threshold drop and non-overlapping intervals.

**Practical guidance:**

- 10–30 cases: directional; expect the gate to pass small drops.
- 50–100 cases: sensitive to 5–8 point regressions.
- 200+ cases: sensitive to 2–3 points, but judge cost grows linearly.

`min_cases` defaults to 10. If your suite is smaller, the gate will tell you it is not making a
regression claim, and that is the honest answer.

## 6. Price the loop, then cache the expensive part

Mock runs are free; live runs are dominated by judge calls. The cache key is
`response + rubric + judge model + prompt version`, so repeated runs with unchanged responses
cost nothing. In the mock walkthrough a cold run makes 40 judge calls and a warm run makes
zero (40/40 hits). With a live judge, that is the difference between paying twice and paying
once for the same PR iteration.

**Decision:** cache scores, not verdicts. Changing a threshold is free; changing a rubric is
not.

## 7. Decide what "ship" means

A feature ships when:

1. the deterministic contract metrics pass on the full suite;
2. the judge passes its threshold on every case, with rationales spot-checked on failures;
3. cost and p95 latency are inside the budgets;
4. a baseline exists and the current run is not a regression;
5. the failure modes in [`failure-modes.md`](failure-modes.md) have an owner.

That is the gate. A green check without a baseline is "first run recorded", not "quality
proven", and the report says so.
