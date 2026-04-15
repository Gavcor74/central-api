from __future__ import annotations

import os

from fastapi import Header, HTTPException


def get_api_key() -> str:
    return os.getenv("API_KEY", "").strip()


def get_auth_config() -> dict[str, object]:
    api_key = get_api_key()
    return {
        "enabled": bool(api_key),
        "has_api_key": bool(api_key),
    }


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    expected = get_api_key()
    if not expected:
        return
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="API key invalida.")
