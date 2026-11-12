# CI integration

EvalGate ships a composite GitHub Action that runs a suite, compares it with a baseline,
uploads artifacts, and posts an idempotent PR comment.

## Minimal workflow

```yaml
name: evals
on: pull_request
permissions:
  contents: read
  pull-requests: write
jobs:
  evalgate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0        # needed to read the baseline from another ref
      - uses: supremeyuma/evalgate@v1
        with:
          suite: examples/support/suite.yaml
          baseline: main
          mock: true            # remove for live provider calls
```

Inside this repository the action is referenced as `uses: ./`; see
[`examples/consumer/.github/workflows/evalgate.yml`](../examples/consumer/.github/workflows/evalgate.yml).

## Inputs

| Input | Default | Meaning |
|---|---|---|
| `suite` | required | Suite YAML path, relative to `working-directory`. |
| `working-directory` | `.` | Directory containing the suite and its assets. |
| `baseline` | `main` | Git ref to load the baseline from, or a report path. `none` disables comparison. |
| `baseline-report` | `.evalgate/baseline.json` | Baseline report path inside the working directory at that ref. |
| `mock` | `false` | Force the deterministic mock provider. |
| `concurrency` | `5` | Maximum in-flight provider calls. |
| `fail-on-regression` | `true` | Propagate the CLI exit code to the job. |
| `comment` | `true` | Post or update the PR comment on `pull_request` events. |
| `github-token` | `${{ github.token }}` | Token for the comment. Read-only tokens skip the comment. |
| `python-version` | `3.12` | Python for the tool environment. |

Outputs: `pass-rate`, `exit-code`, `report-json`, `report-html`.

## Baseline maintenance

The action reads `.evalgate/baseline.json` from the baseline ref (for a PR, the base branch).
To establish or refresh it:

```powershell
uv run evalgate run examples/support/suite.yaml --mock --json examples/support/.evalgate/baseline.json
```

Commit that file on the base branch. Without it the first run is recorded as a baseline-less
run and the action prints a note. Passing `baseline: path/to/report.json` compares against a
report inside the checked-out workspace instead.

## Artifacts and the comment

- `reports/evalgate.json` — stable report schema (`schema_version: 1`).
- `reports/evalgate.html` — self-contained HTML with per-case diffs and judge rationales.
- The comment contains a pass/fail header, a metric table (baseline, current, delta, verdict),
  hard-limit notices, judge cache stats, and up to ten regressed cases. It is located by the
  marker `<!-- evalgate:report -->` and updated in place, so a PR has exactly one comment.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Pass |
| 1 | Gate failure: hard limit, real regression, or (first run) failing cases |
| 2 | Invalid suite or configuration |
| 3 | Infrastructure failure (provider/judge/template error) |

`fail-on-regression: false` lets a workflow publish the report without blocking the merge;
the exit code is still available as an output.

## Live providers

Remove `mock: true` and set the provider key as a repository secret. The suite's `model`
block chooses the provider. Keep a keyless mock job as a required check so forks and
dependabot PRs stay green; run the live job conditionally:

```yaml
      - uses: supremeyuma/evalgate@v1
        if: ${{ secrets.OPENAI_API_KEY != '' }}
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

## Offline dry run

`scripts/demo_ci.ps1` reproduces the action's steps locally with the mock provider: validate,
load the committed baseline, run, render the comment, and print artifact paths. Use it when
Docker or `act` is unavailable.
