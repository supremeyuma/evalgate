"""Export the FastAPI OpenAPI document for review and drift checks."""

from __future__ import annotations

import json
from pathlib import Path

from evalgate.api.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    document = create_app().openapi()
    destination = ROOT / "docs" / "openapi.json"
    destination.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {destination}")


if __name__ == "__main__":
    main()
