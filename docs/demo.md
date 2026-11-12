# Demo

Everything below is offline (`--mock`), deterministic, and keyless.

## The regression demo

```powershell
uv run python scripts/demo_regression.py
```

1. Runs `examples/support/suite.yaml` (40 cases) with the healthy prompt → exit 0, 100% pass.
2. Runs the same suite with `--prompt-variant weakened --baseline <first report>` → exit 1.
3. Writes `reports/demo-baseline.{json,html}`, `reports/demo-weakened.{json,html}`, and
   `reports/demo-comment.md`.

Observed:

```
baseline pass rate: 100.0% (exit 0)
weakened pass rate: 0.0% (exit 1)
failing cases: 40
  - sup-001: json_schema_valid: response does not contain parseable JSON; contains: missing
    'answer', 'citations', 'confidence'; llm_judge: score 1/5 vs threshold 4
reports: demo-baseline.json, demo-weakened.json, demo-comment.md
DEMO PASSED: the gate blocked the weakened prompt.
```

The comment starts with:

```
<!-- evalgate:report -->
## EvalGate - :x: failed
| Pass rate | 100.0% | 0.0% | -100.0 pp | :x: regression |
```

## Cache demo

```powershell
uv run evalgate run examples/support/suite.yaml --mock --json reports/r1.json
uv run evalgate run examples/support/suite.yaml --mock --json reports/r2.json
```

Cold: 40 judge calls, 0 hits. Warm: 0 calls, 40 hits. Both cost $0 with the mock provider; the
hit counts are the measurable part.

## Hard-limit demo

The mock provider costs $0, so the equivalent hard-limit demonstration uses latency:

```powershell
# add `limits: {max_p95_latency_ms: 10}` to a copy of the suite, then:
uv run evalgate run suite.yaml --mock --mock-latency-ms 50
```

Exit 1 with `hard limit: p95 latency ... exceeds ...`, not a regression message. The cost path
is covered by a unit test with a priced completion.

## API demo

```powershell
docker compose up --build
curl -X POST http://localhost:8001/v1/runs `
  -H "X-API-Key: dev-key" -H "Content-Type: application/json" `
  -d '{"suite":"examples/support/suite.yaml","mock":true}'
# poll the returned id:
curl -H "X-API-Key: dev-key" http://localhost:8001/v1/runs/<id>
```

The run executes inline for a predictable demo; the ARQ worker is the queue path.

## Recording the GIF (human step)

`scripts/demo.tape` is a [VHS](https://github.com/charmbracelet/vhs) script. Recording and
uploading the GIF is the one step that needs a human (and `vhs` installed):

```powershell
vhs scripts/demo.tape
```

This produces `docs/demo.gif`. Until it is recorded, this document is the demo, and every
command in it is reproducible.
