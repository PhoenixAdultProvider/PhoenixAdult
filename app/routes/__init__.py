from __future__ import annotations

from fastapi.responses import JSONResponse
from pydantic import BaseModel


def plex_json(model: BaseModel, status_code: int = 200) -> JSONResponse:
    """Serialise a Plex response model, omitting unset optionals (matching the TS output)."""
    return JSONResponse(model.model_dump(by_alias=True, exclude_none=True), status_code=status_code)
