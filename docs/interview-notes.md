# Interview notes

Condensed answers to the questions this project is designed to provoke.

## Data model sketch

```
suites(id, name, yaml, created_at)
runs(id, suite_id, suite_path, commit_sha, git_ref, baseline_run_id, status,
     mode, pass_rate, wilson_low, wilson_high, total_cases, cost_usd,
     p95_latency_ms, started_at, finished_at, report jsonb)
results(id, run_id, case_id, metric, score, passed, latency_ms, cost_usd,
        detail, judge_output jsonb, response)   -- unique(run_id, case_id, metric)
judge_cache(hash pk, response_hash, rubric_hash, model, score, rationale,
            confidence, cost_usd, created_at)
```

A run is immutable after finalization; a retry upserts `(run_id, case_id, metric)` rather than
duplicating. `runs.report` stores the exact artifact for API/report retrieval, while `results`
supports queries ("which metric regressed across runs") without parsing JSON.

## Precision/recall for classification

For a label like `billing`, define:

- **precision** = correctly predicted billing / all predicted billing. Low precision means the
  feature misroutes tickets into billing and wastes the billing team's time.
- **recall** = correctly predicted billing / all actual billing. Low recall means billing
  tickets land elsewhere and customers wait.

The classification example uses exact match, which optimizes accuracy. In production I would add
per-label precision/recall to the report (from the confusion matrix) because the cost of a false
positive is not the cost of a false negative. The gate would then assert per-label floors, not
just overall accuracy. That is a deliberate "what's next", not a hidden claim.

## Sample-size argument

Pass rate is a binomial proportion. At 40 cases and 100%, the Wilson 95% interval is about
91.2–100%; at 80% it is about 65–90%. The width is driven by `1/sqrt(n)`, which is why:

- a 2.5-point drop (one case at n=40) cannot be distinguished from noise;
- a 10-point drop at n=40 still overlaps in many configurations;
- the gate needs both a threshold and interval separation, and `min_cases` below which it
  explicitly refuses to call a regression.

If a team needs 2-point sensitivity, the suite needs hundreds of cases or paired comparisons.
Publishing a number without its interval is the mistake, not having a small suite.

## Judge failure modes

1. **Malformed output** — prose, fences, wrong types. Mitigation: extract JSON, strict Pydantic,
   one repair attempt with the validation error, then fail the case with `judge_error`.
2. **Refusal** — "I cannot evaluate this." Mitigation: score 1 with `refusal: true`, documented.
3. **Anchoring drift** — the judge rewards confidence or style. Mitigation: explicit anchors,
   instructions to ignore style, calibration against a second judge, and storing rationales.
4. **Position/verbosity bias** — longer answers score higher. Mitigation: rubrics focus on
   required facts and actionability; pairwise mode is future work.
5. **Cache staleness** — a new rubric served from an old key. Mitigation: rubric hash and prompt
   version in the key; cache invalidation is deliberate.

## Three production failure modes and responses

- **Provider outage:** per-case provider errors, exit 3, no silent pass. Re-run when healthy;
  the report marks each errored case.
- **Cost blow-up:** pricing per model with `effective_date`, per-case and per-run cost limits,
  and unknown models cost 0 with a warning rather than a crash. A cost breach fails independently
  of pass rate.
- **Flaky judge:** judge calls are cached; reruns reuse scores. A verdict flip on an unchanged
  response cannot happen from the judge path — it would require a rubric/model/prompt change,
  which is visible in the key.

## Trade-offs I would defend

- No web UI: the CLI and PR comment are where the decision happens.
- No agent framework: two HTTP contracts are simpler than a framework's retry/callback model.
- Strict YAML: a typo should fail validation, not silently disable a metric.
- Exit 3 on errors: stricter than "mark flaky and pass", because a gate must not pass when it
  could not measure.
- Per-case requirements over a weighted score: the diff is the product.

## What the numbers do and do not show

The committed numbers are mock-derived. They prove determinism, concurrency bounds, cache
behavior, and report stability. They do not measure a real model's quality or a live cost.
Live numbers require a key; the README says so explicitly rather than mixing the two.
