# Failure modes and the flaky-run policy

EvalGate is a gate, so its failure behavior matters as much as its pass behavior. Every
failure below is exercised by a test; this document explains what a maintainer should do.

## Provider failures

| Failure | Behavior | Exit code |
|---|---|---|
| HTTP 429 | Retried up to 4 attempts with exponential backoff and jitter; `Retry-After` is honored and capped at 8 s. | — |
| HTTP 5xx | Same retry policy. | — |
| Timeout / connection error | Same retry policy. | — |
| 429/5xx/timeout after every attempt | The case is recorded as a provider error; the run cannot be trusted. | 3 |
| Non-retryable 4xx | Typed `ProviderRequestError`; the case fails immediately. | 3 |
| Malformed response body | `ProviderResponseError`; the case fails. | 3 |
| Missing `usage` | Tokens count as 0, cost as 0, and a warning is logged; the run continues. | 0/1 |
| Unknown model in the pricing table | Cost is 0 with a structured warning; the run continues. | 0/1 |

Any errored case makes the run exit 3 rather than 1. A regression computed from a partial
run would be misleading; the right response is to re-run once the provider is healthy.

## Judge failures

| Failure | Behavior |
|---|---|
| Malformed JSON, prose, or code fences | One repair attempt with the parser error appended to the prompt. |
| Still malformed after repair | `judge_error` on the case; the case fails; the run continues. |
| Score out of range / wrong type / missing field | Treated as malformed; repair path applies. Pydantic strict mode rejects `"4"`. |
| Refusal ("I cannot evaluate this") | Score 1 with `refusal: true` in the stored judge output and an explicit detail string. |
| Judge provider error | `judge_error` on the case; no crash. |
| Cache hit | No provider call; the stored score is re-thresholded with the current threshold. |

## Regression false positives and flakes

The regression rule requires **both** a drop beyond `max_pass_rate_drop` and non-overlapping
Wilson 95% intervals, with at least `min_cases` in both runs. A 3-point drop on 12 cases is
reported but does not fail the build.

Policy for flaky evaluations:

- Provider and judge errors are retried once at the transport level, and judge parse errors
  get one repair call.
- If a case still errors, the run exits 3. We deliberately do **not** convert an errored run
  into a passing one: an infrastructure failure is visible in the PR, and the author re-runs.
- Re-run a failed job once before treating it as a quality signal. If the verdict flips and
  the second run is green, comment with both run links rather than silently merging.
- Judge nondeterminism is reduced by `temperature=0` and anchored rubrics, not by averaging
  multiple runs. Calibrate judges with `evalgate calibrate` when changing a rubric.

This is stricter than "mark flaky and pass". The deviation is intentional: a gate that
passes when its judge is down is not a gate.

## Configuration and cache failures

| Failure | Behavior |
|---|---|
| Invalid suite / unknown key | Exit 2 with a field-level message; no provider call. |
| Missing prompt, dataset, schema, or rubric | Exit 2 naming the field and path. |
| Path traversal or absolute path | Exit 2; the path never leaves the project root. |
| Missing baseline (`--baseline` path) | Exit 2. The action treats an absent baseline as a note and runs without one. |
| Rubric edited | Cache key changes; judgments are recomputed. |
| Threshold edited | Cache remains valid; the stored score is re-thresholded. |
| Judge prompt contract edited without a version bump | Stale scores possible; bump `JUDGE_PROMPT_VERSION`. |

## Token and fork behavior

- The PR comment step skips with a notice when the token is read-only (fork PRs). Artifacts
  and the exit code still work.
- The action never requires a provider secret to run: `mock: true` is the reproducible path.
- API keys are read from the environment and never written to reports or logs.

## Reporting failures

| Failure | Behavior |
|---|---|
| HTML/JSON write error | Exit 2 with the path in the message. |
| Report missing when commenting | The comment step logs and exits 0. |
| GitHub API error when commenting | The comment step logs and exits 0; the gate result is unaffected. |
