"""Reproduce the flagship demo: a healthy run, then a weakened prompt that the gate blocks.

Usage: uv run python scripts/demo_regression.py
Both runs use the deterministic mock provider, so no API key or network is required.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from evalgate.models.result import RunReport
from evalgate.report.pr_comment import render_pr_comment

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
SUITE = ROOT / "examples" / "support" / "suite.yaml"
BASELINE = REPORTS / "demo-baseline.json"
WEAKENED = REPORTS / "demo-weakened.json"
COMMENT = REPORTS / "demo-comment.md"


def run_cli(args: list[str]) -> int:
    process = subprocess.run([sys.executable, "-m", "evalgate", *args], cwd=ROOT, check=False)
    return process.returncode


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    for path in (
        BASELINE,
        Path(str(BASELINE).replace(".json", ".html")),
        WEAKENED,
        Path(str(WEAKENED).replace(".json", ".html")),
        COMMENT,
    ):
        path.unlink(missing_ok=True)

    print("== baseline run (mock, healthy prompt) ==")
    baseline_code = run_cli(
        [
            "run",
            str(SUITE),
            "--mock",
            "--json",
            str(BASELINE),
            "--html",
            str(Path(str(BASELINE).replace(".json", ".html"))),
        ]
    )
    if baseline_code != 0:
        print(f"unexpected baseline exit {baseline_code}")
        return 1

    print("\n== weakened prompt, compared with the baseline ==")
    weakened_code = run_cli(
        [
            "run",
            str(SUITE),
            "--mock",
            "--prompt-variant",
            "weakened",
            "--baseline",
            str(BASELINE),
            "--json",
            str(WEAKENED),
            "--html",
            str(Path(str(WEAKENED).replace(".json", ".html"))),
        ]
    )

    baseline_report = RunReport.model_validate_json(BASELINE.read_text(encoding="utf-8"))
    weakened_report = RunReport.model_validate_json(WEAKENED.read_text(encoding="utf-8"))
    COMMENT.write_text(
        render_pr_comment(
            weakened_report,
            baseline=baseline_report,
            artifact_url="file://reports/demo-weakened.html",
        ),
        encoding="utf-8",
        newline="\n",
    )

    failing = [case for case in weakened_report.cases if not case.passed]
    print("\n== result ==")
    print(f"baseline pass rate: {baseline_report.summary.pass_rate:.1%} (exit {baseline_code})")
    print(f"weakened pass rate: {weakened_report.summary.pass_rate:.1%} (exit {weakened_code})")
    print(f"failing cases: {len(failing)}")
    for case in failing[:5]:
        detail = case.error or "; ".join(
            f"{metric.metric}: {metric.detail}" for metric in case.metrics if not metric.passed
        )
        print(f"  - {case.case_id}: {detail}")
    print(f"reports: {BASELINE.name}, {WEAKENED.name}, {COMMENT.name}")

    if baseline_code == 0 and weakened_code == 1:
        print("\nDEMO PASSED: the gate blocked the weakened prompt.")
        return 0
    print("\nDEMO FAILED: expected baseline exit 0 and weakened exit 1.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
