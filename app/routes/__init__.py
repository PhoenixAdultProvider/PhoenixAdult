from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


def plex_json(model: BaseModel, status_code: int = 200) -> JSONResponse:
    """Serialise a Plex response model, omitting unset optionals."""
    return JSONResponse(model.model_dump(by_alias=True, exclude_none=True), status_code=status_code)


async def read_json_body(request: Request) -> dict[str, Any]:
    """Parsed JSON request body, or {} for a missing/non-JSON/non-object body."""
    try:
        data = await request.json()
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}
