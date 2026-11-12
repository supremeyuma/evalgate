"""Suite loading, path resolution, and validation.

All file references in a suite are resolved relative to the suite file and must stay
inside the project root (the nearest ancestor containing ``.git``, or the suite's own
directory when the suite lives outside a repository). Absolute paths and ``..`` escapes
are rejected so a suite cannot exfiltrate files from the runner's machine.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import jsonschema
import yaml
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, ConfigDict, ValidationError

from evalgate.models.case import Case
from evalgate.models.suite import JsonSchemaValidSpec, LlmJudgeSpec, Suite

_JSONL_SUFFIXES = frozenset({".jsonl", ".ndjson"})


class SuiteLoadError(Exception):
    """A suite file, dataset, or referenced asset could not be loaded."""


class LoadedSuite(BaseModel):
    """A suite plus every asset it references, resolved and validated."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    path: Path
    root: Path
    suite: Suite
    prompt_text: str
    cases: list[Case]
    schema_documents: dict[str, dict[str, Any]]
    rubric_texts: dict[str, str]


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return start


def _is_within(candidate: Path, parent: Path) -> bool:
    candidate_key = os.path.normcase(str(candidate))
    parent_key = os.path.normcase(str(parent))
    try:
        return os.path.commonpath([candidate_key, parent_key]) == parent_key
    except ValueError:  # different drives on Windows
        return False


def _format_validation_error(error: ValidationError) -> str:
    details: list[str] = []
    for item in error.errors():
        location = ".".join(str(part) for part in item["loc"]) or "<root>"
        details.append(f"{location}: {item['msg']}")
    return "; ".join(details)


def _resolve_asset(raw_path: str, *, suite_dir: Path, root: Path, field: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        message = f"{field}: absolute paths are not allowed ({raw_path})"
        raise SuiteLoadError(message)

    resolved = (suite_dir / candidate).resolve()
    if not _is_within(resolved, root):
        message = f"{field}: path escapes the project root ({raw_path})"
        raise SuiteLoadError(message)
    return resolved


def _read_text(path: Path, *, field: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        message = f"{field}: file not found: {path}"
        raise SuiteLoadError(message) from error
    except OSError as error:
        message = f"{field}: could not read {path}: {error}"
        raise SuiteLoadError(message) from error


def _load_cases(path: Path, *, field: str) -> list[Case]:
    if path.suffix.lower() not in _JSONL_SUFFIXES:
        message = f"{field}: cases file must be JSONL (.jsonl/.ndjson): {path.name}"
        raise SuiteLoadError(message)

    cases: list[Case] = []
    seen: set[str] = set()
    for line_number, line in enumerate(_read_text(path, field=field).splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as error:
            message = f"{field}: line {line_number}: invalid JSON: {error.msg}"
            raise SuiteLoadError(message) from error
        if not isinstance(payload, dict):
            message = f"{field}: line {line_number}: each case must be a JSON object"
            raise SuiteLoadError(message)
        try:
            case = Case.model_validate(payload)
        except ValidationError as error:
            message = f"{field}: line {line_number}: {_format_validation_error(error)}"
            raise SuiteLoadError(message) from error
        if case.id in seen:
            message = f"{field}: line {line_number}: duplicate case id {case.id!r}"
            raise SuiteLoadError(message)
        seen.add(case.id)
        cases.append(case)

    if not cases:
        message = f"{field}: dataset contains no cases: {path.name}"
        raise SuiteLoadError(message)
    return cases


def _load_json_document(path: Path, *, field: str) -> dict[str, Any]:
    try:
        document = json.loads(_read_text(path, field=field))
    except json.JSONDecodeError as error:
        message = f"{field}: invalid JSON in {path.name}: {error.msg}"
        raise SuiteLoadError(message) from error
    if not isinstance(document, dict):
        message = f"{field}: JSON Schema must be an object: {path.name}"
        raise SuiteLoadError(message)
    return document


def load_suite(path: str | Path, *, root: str | Path | None = None) -> LoadedSuite:
    """Load and fully validate a suite file and every asset it references."""

    suite_path = Path(path).expanduser().resolve()
    if not suite_path.is_file():
        message = f"suite file not found: {suite_path}"
        raise SuiteLoadError(message)

    suite_dir = suite_path.parent
    project_root = Path(root).expanduser().resolve() if root else _find_repo_root(suite_dir)
    if not _is_within(suite_path, project_root):
        message = f"suite file is outside the project root: {suite_path}"
        raise SuiteLoadError(message)

    try:
        raw = yaml.safe_load(_read_text(suite_path, field="suite"))
    except yaml.YAMLError as error:
        message = f"invalid YAML in {suite_path.name}: {error}"
        raise SuiteLoadError(message) from error
    if not isinstance(raw, dict):
        message = f"{suite_path.name}: suite file must contain a YAML mapping"
        raise SuiteLoadError(message)

    try:
        suite = Suite.model_validate(raw)
    except ValidationError as error:
        message = f"{suite_path.name}: {_format_validation_error(error)}"
        raise SuiteLoadError(message) from error

    def resolve(value: str, field: str) -> Path:
        return _resolve_asset(value, suite_dir=suite_dir, root=project_root, field=field)

    prompt_path = resolve(suite.prompt, "prompt")
    prompt_text = _read_text(prompt_path, field="prompt")

    cases_path = resolve(suite.cases_file, "cases_file")
    cases = _load_cases(cases_path, field="cases_file")

    schema_documents: dict[str, dict[str, Any]] = {}
    for index, metric in enumerate(suite.metrics):
        if not isinstance(metric, JsonSchemaValidSpec):
            continue
        if metric.schema_path in schema_documents:
            continue
        field = f"metrics[{index}].schema"
        document = _load_json_document(resolve(metric.schema_path, field), field=field)
        try:
            jsonschema.validators.validator_for(document).check_schema(document)
        except SchemaError as error:
            message = f"{field}: invalid JSON Schema: {error.message}"
            raise SuiteLoadError(message) from error
        schema_documents[metric.schema_path] = document

    rubric_texts: dict[str, str] = {}
    for index, metric in enumerate(suite.metrics):
        if not isinstance(metric, LlmJudgeSpec):
            continue
        rubric = metric.rubric or suite.judge.rubric
        if rubric is None:  # guarded by Suite validation
            message = f"metrics[{index}].rubric: no rubric configured"
            raise SuiteLoadError(message)
        if rubric in rubric_texts:
            continue
        rubric_texts[rubric] = _read_text(
            resolve(rubric, f"metrics[{index}].rubric"), field=f"metrics[{index}].rubric"
        )

    return LoadedSuite(
        path=suite_path,
        root=project_root,
        suite=suite,
        prompt_text=prompt_text,
        cases=cases,
        schema_documents=schema_documents,
        rubric_texts=rubric_texts,
    )
