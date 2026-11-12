"""FastAPI dependencies: settings, repository, and API-key auth."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Header, HTTPException, Request, status

from evalgate.config import Settings
from evalgate.storage.repository import RunRepository


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_repository(request: Request) -> RunRepository:
    repository: RunRepository = request.app.state.repository
    return repository


async def require_api_key(
    request: Request,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    """Reject requests without the configured ``X-API-Key``."""

    expected = get_app_settings(request).evalgate_api_key
    if x_api_key is None or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing X-API-Key",
        )
