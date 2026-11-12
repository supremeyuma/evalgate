"""API auth, run lifecycle, reports, and health endpoints against Postgres."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from evalgate.api.main import create_app
from evalgate.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
SUPPORT_SUITE = REPO_ROOT / "examples" / "support" / "suite.yaml"
AUTH = {"X-API-Key": "test-key"}


def test_health_endpoints(api_settings: Settings) -> None:
    with TestClient(create_app(api_settings)) as client:
        assert client.get("/healthz").status_code == 200
        ready = client.get("/readyz")
        assert ready.status_code == 200
        assert ready.json()["status"] == "ready"


def test_run_requires_api_key(api_settings: Settings) -> None:
    with TestClient(create_app(api_settings)) as client:
        response = client.post("/v1/runs", json={"suite": str(SUPPORT_SUITE), "mock": True})
        assert response.status_code == 401


def test_run_lifecycle_and_reports(api_settings: Settings) -> None:
    with TestClient(create_app(api_settings)) as client:
        created = client.post(
            "/v1/runs",
            headers=AUTH,
            json={"suite": str(SUPPORT_SUITE), "mock": True, "git_ref": "main"},
        )
        assert created.status_code == 201, created.text
        payload = created.json()
        assert payload["status"] == "passed"
        assert payload["pass_rate"] == 1.0
        assert payload["exit_code"] == 0
        run_id = payload["id"]

        run = client.get(f"/v1/runs/{run_id}", headers=AUTH)
        assert run.status_code == 200
        assert run.json()["summary"]["total"] == 40
        assert run.json()["status"] == "passed"

        report = client.get(f"/v1/runs/{run_id}/report.json", headers=AUTH)
        assert report.status_code == 200
        assert report.json()["summary"]["total"] == 40

        html = client.get(f"/v1/runs/{run_id}/report.html", headers=AUTH)
        assert html.status_code == 200
        assert "support-reply-quality" in html.text

        listed = client.get("/v1/runs", headers=AUTH)
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        missing = client.get(f"/v1/runs/{run_id[:-1]}0", headers=AUTH)
        assert missing.status_code == 404


def test_inline_yaml_run(api_settings: Settings, tmp_path: Path) -> None:
    (tmp_path / "prompt.md").write_text("{{ input }}", encoding="utf-8")
    (tmp_path / "cases.jsonl").write_text(
        '{"id": "a", "input": "hi", "expected": "ok"}\n', encoding="utf-8"
    )
    inline = """
name: inline-suite
model:
  provider: mock
  name: mock
prompt: prompt.md
cases_file: cases.jsonl
metrics:
  - type: exact_match
"""
    with TestClient(create_app(api_settings)) as client:
        response = client.post(
            "/v1/runs",
            headers=AUTH,
            json={
                "suite_yaml": inline,
                "working_directory": str(tmp_path),
                "mock": True,
            },
        )
        assert response.status_code == 201, response.text
        assert response.json()["pass_rate"] == 1.0

    assert not list(tmp_path.glob(".evalgate-inline-*.yaml"))


def test_invalid_suite_returns_400(api_settings: Settings, tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: broken\n", encoding="utf-8")
    with TestClient(create_app(api_settings)) as client:
        response = client.post("/v1/runs", headers=AUTH, json={"suite": str(bad), "mock": True})
        assert response.status_code == 400


def test_body_requires_exactly_one_source(api_settings: Settings) -> None:
    with TestClient(create_app(api_settings)) as client:
        response = client.post(
            "/v1/runs",
            headers=AUTH,
            json={"suite": str(SUPPORT_SUITE), "suite_yaml": "name: x"},
        )
        assert response.status_code == 422


def test_openapi_document(api_settings: Settings) -> None:
    with TestClient(create_app(api_settings)) as client:
        schema: dict[str, Any] = client.get("/openapi.json").json()
        assert "/v1/runs" in schema["paths"]
        assert "X-API-Key" in json.dumps(schema)
