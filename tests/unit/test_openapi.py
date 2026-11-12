"""The committed OpenAPI document must match the app."""

from __future__ import annotations

import json
from pathlib import Path

from evalgate.api.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_openapi_document_matches_committed_copy() -> None:
    generated = json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"
    committed = (REPO_ROOT / "docs" / "openapi.json").read_text(encoding="utf-8")
    assert generated == committed, (
        "docs/openapi.json is stale; run `uv run python scripts/export_openapi.py`"
    )
