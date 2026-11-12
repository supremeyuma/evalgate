"""Tests for suite loading, dataset parsing, and path safety."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evalgate.models.loader import SuiteLoadError, load_suite

VALID_SUITE = """
name: demo
model:
  provider: mock
  name: m
prompt: prompt.md
cases_file: cases.jsonl
metrics:
  - type: exact_match
"""


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _suite_file(tmp_path: Path, yaml_text: str = VALID_SUITE) -> Path:
    return _write(tmp_path / "suite.yaml", yaml_text)


def _default_assets(tmp_path: Path) -> None:
    _write(tmp_path / "prompt.md", "Hello {{ input }}")
    _write(
        tmp_path / "cases.jsonl",
        '{"id": "a", "input": "hi", "expected": "hi"}\n'
        '{"id": "b", "input": "bye", "expected": "bye"}\n',
    )


def test_loads_valid_suite(tmp_path: Path) -> None:
    _default_assets(tmp_path)
    loaded = load_suite(_suite_file(tmp_path))
    assert loaded.suite.name == "demo"
    assert [case.id for case in loaded.cases] == ["a", "b"]
    assert loaded.prompt_text.startswith("Hello")
    assert loaded.root == tmp_path


def test_missing_suite_file(tmp_path: Path) -> None:
    with pytest.raises(SuiteLoadError, match="suite file not found"):
        load_suite(tmp_path / "nope.yaml")


def test_unknown_key_reports_location(tmp_path: Path) -> None:
    _default_assets(tmp_path)
    path = _suite_file(tmp_path, VALID_SUITE + "mystery: 1\n")
    with pytest.raises(SuiteLoadError, match="mystery: Extra inputs"):
        load_suite(path)


def test_missing_prompt_is_clear(tmp_path: Path) -> None:
    _write(tmp_path / "cases.jsonl", '{"id": "a", "input": "hi"}\n')
    with pytest.raises(SuiteLoadError, match="prompt: file not found"):
        load_suite(_suite_file(tmp_path))


def test_missing_dataset_is_clear(tmp_path: Path) -> None:
    _write(tmp_path / "prompt.md", "hi")
    with pytest.raises(SuiteLoadError, match="cases_file: file not found"):
        load_suite(_suite_file(tmp_path))


def test_duplicate_case_ids_rejected(tmp_path: Path) -> None:
    _write(tmp_path / "prompt.md", "hi")
    _write(
        tmp_path / "cases.jsonl",
        '{"id": "a", "input": "one"}\n{"id": "a", "input": "two"}\n',
    )
    with pytest.raises(SuiteLoadError, match="duplicate case id 'a'"):
        load_suite(_suite_file(tmp_path))


def test_invalid_jsonl_reports_line(tmp_path: Path) -> None:
    _write(tmp_path / "prompt.md", "hi")
    _write(tmp_path / "cases.jsonl", '{"id": "a", "input": "one"}\nnot json\n')
    with pytest.raises(SuiteLoadError, match="line 2: invalid JSON"):
        load_suite(_suite_file(tmp_path))


def test_non_object_jsonl_rejected(tmp_path: Path) -> None:
    _write(tmp_path / "prompt.md", "hi")
    _write(tmp_path / "cases.jsonl", '["a"]\n')
    with pytest.raises(SuiteLoadError, match="must be a JSON object"):
        load_suite(_suite_file(tmp_path))


def test_dataset_requires_jsonl_suffix(tmp_path: Path) -> None:
    _write(tmp_path / "prompt.md", "hi")
    _write(tmp_path / "cases.txt", '{"id": "a", "input": "x"}\n')
    path = _suite_file(tmp_path, VALID_SUITE.replace("cases.jsonl", "cases.txt"))
    with pytest.raises(SuiteLoadError, match="must be JSONL"):
        load_suite(path)


def test_empty_dataset_rejected(tmp_path: Path) -> None:
    _write(tmp_path / "prompt.md", "hi")
    _write(tmp_path / "cases.jsonl", "\n\n")
    with pytest.raises(SuiteLoadError, match="contains no cases"):
        load_suite(_suite_file(tmp_path))


def test_path_traversal_rejected(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write(tmp_path / "outside.md", "secret")
    path = _suite_file(project, VALID_SUITE.replace("prompt.md", "../outside.md"))
    with pytest.raises(SuiteLoadError, match="escapes the project root"):
        load_suite(path)


def test_absolute_prompt_path_rejected(tmp_path: Path) -> None:
    _default_assets(tmp_path)
    absolute = tmp_path / "prompt.md"
    yaml_text = VALID_SUITE.replace("prompt.md", absolute.as_posix())
    with pytest.raises(SuiteLoadError, match="absolute paths are not allowed"):
        load_suite(_suite_file(tmp_path, yaml_text))


def test_schemas_must_validate(tmp_path: Path) -> None:
    _write(tmp_path / "prompt.md", "hi")
    _write(tmp_path / "cases.jsonl", '{"id": "a", "input": "hi"}\n')
    _write(tmp_path / "schema.json", '{"type": "not-a-real-type"}')
    yaml_text = VALID_SUITE.replace(
        "  - type: exact_match",
        "  - type: json_schema_valid\n    schema: schema.json",
    )
    with pytest.raises(SuiteLoadError, match="invalid JSON Schema"):
        load_suite(_suite_file(tmp_path, yaml_text))


def test_malformed_schema_json_rejected(tmp_path: Path) -> None:
    _write(tmp_path / "prompt.md", "hi")
    _write(tmp_path / "cases.jsonl", '{"id": "a", "input": "hi"}\n')
    _write(tmp_path / "schema.json", "{not json")
    yaml_text = VALID_SUITE.replace(
        "  - type: exact_match",
        "  - type: json_schema_valid\n    schema: schema.json",
    )
    with pytest.raises(SuiteLoadError, match="invalid JSON"):
        load_suite(_suite_file(tmp_path, yaml_text))


def test_rubric_loaded(tmp_path: Path) -> None:
    _write(tmp_path / "prompt.md", "hi")
    _write(tmp_path / "cases.jsonl", '{"id": "a", "input": "hi"}\n')
    _write(tmp_path / "rubric.md", "Anchors")
    yaml_text = VALID_SUITE.replace(
        "  - type: exact_match",
        "  - type: llm_judge\n    rubric: rubric.md\n    threshold: 4",
    )
    loaded = load_suite(_suite_file(tmp_path, yaml_text))
    assert loaded.rubric_texts == {"rubric.md": "Anchors"}


def test_missing_rubric_is_clear(tmp_path: Path) -> None:
    _write(tmp_path / "prompt.md", "hi")
    _write(tmp_path / "cases.jsonl", '{"id": "a", "input": "hi"}\n')
    yaml_text = VALID_SUITE.replace(
        "  - type: exact_match",
        "  - type: llm_judge\n    rubric: missing.md\n    threshold: 4",
    )
    with pytest.raises(SuiteLoadError, match=r"metrics\[0\].rubric: file not found"):
        load_suite(_suite_file(tmp_path, yaml_text))


def test_yaml_must_be_mapping(tmp_path: Path) -> None:
    path = _suite_file(tmp_path, "- just\n- a list\n")
    with pytest.raises(SuiteLoadError, match="must contain a YAML mapping"):
        load_suite(path)


def test_invalid_yaml_is_clear(tmp_path: Path) -> None:
    path = _suite_file(tmp_path, "name: [unclosed\n")
    with pytest.raises(SuiteLoadError, match="invalid YAML"):
        load_suite(path)


def test_repo_root_allows_parent_reference(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    examples = tmp_path / "examples"
    examples.mkdir()
    _write(tmp_path / "shared" / "prompt.md", "shared")
    _write(examples / "cases.jsonl", '{"id": "a", "input": "hi"}\n')
    path = _write(
        examples / "suite.yaml",
        VALID_SUITE.replace("prompt.md", "../shared/prompt.md"),
    )
    loaded = load_suite(path)
    assert loaded.root == tmp_path
    assert loaded.prompt_text == "shared"


def test_explicit_root_boundary(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write(project / "prompt.md", "hi")
    _write(project / "cases.jsonl", '{"id": "a", "input": "hi"}\n')
    path = _suite_file(project)
    loaded = load_suite(path, root=tmp_path)
    assert loaded.root == tmp_path


def test_cases_carry_context_and_tags(tmp_path: Path) -> None:
    _write(tmp_path / "prompt.md", "hi")
    _write(
        tmp_path / "cases.jsonl",
        json.dumps(
            {
                "id": "a",
                "input": "hi",
                "context": "policy",
                "tags": ["refund"],
            }
        )
        + "\n",
    )
    loaded = load_suite(_suite_file(tmp_path))
    assert loaded.cases[0].context == "policy"
    assert loaded.cases[0].tags == ["refund"]
