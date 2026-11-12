"""Shared fixtures for provider, metric, and runner tests."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from evalgate.models.case import Case
from evalgate.models.loader import LoadedSuite, load_suite
from evalgate.models.suite import ModelSpec


@pytest.fixture
def case() -> Case:
    return Case(id="case-1", input="Say hello", expected="hello", context="policy")


@pytest.fixture
def model() -> ModelSpec:
    return ModelSpec(provider="openai-compatible", name="gpt-4.1-mini")


MakeSuite = Callable[..., LoadedSuite]


@pytest.fixture
def make_suite(tmp_path: Path) -> MakeSuite:
    """Write a suite/dataset/prompt in a temp directory and load it."""

    def factory(
        *,
        cases: list[dict[str, object]] | None = None,
        metrics: str = "  - type: exact_match\n",
        suite_extra: str = "",
        prompt: str = "{{ input }}",
        cases_suffix: str = ".jsonl",
        extra_files: dict[str, str] | None = None,
        provider: str = "mock",
        model_name: str = "test-model",
    ) -> LoadedSuite:
        project = tmp_path / "project"
        project.mkdir(exist_ok=True)
        (project / "prompt.md").write_text(prompt, encoding="utf-8")
        for name, content in (extra_files or {}).items():
            (project / name).write_text(content, encoding="utf-8")
        rows = cases or [
            {"id": "a", "input": "one", "expected": "ok"},
            {"id": "b", "input": "two", "expected": "ok"},
        ]
        lines = [json.dumps(row, ensure_ascii=False) for row in rows]
        (project / f"cases{cases_suffix}").write_text(
            "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
        )
        yaml_text = (
            "name: test-suite\n"
            "model:\n"
            f"  provider: {provider}\n"
            f"  name: {model_name}\n"
            f"prompt: prompt.md\n"
            f"cases_file: cases{cases_suffix}\n"
            "metrics:\n"
            f"{metrics}"
            f"{suite_extra}"
        )
        suite_path = project / "suite.yaml"
        suite_path.write_text(yaml_text, encoding="utf-8", newline="\n")
        return load_suite(suite_path)

    return factory
