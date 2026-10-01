from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from fastapi import Request
from fastapi.responses import Response

_IMMUTABLE = 'public, max-age=31536000, immutable'
_REVALIDATE = 'public, max-age=60'


@lru_cache(maxsize=32)
def _read(path: Path, mtime_ns: int) -> tuple[bytes, str]:
    data = path.read_bytes()
    return data, hashlib.sha256(data).hexdigest()[:8]


def _load(path: Path) -> tuple[bytes, str]:
    return _read(path, path.stat().st_mtime_ns)


def asset_bytes(path: Path) -> bytes:
    return _load(path)[0]


def asset_version(path: Path) -> str:
    return _load(path)[1]


def asset_response(path: Path, request: Request, requested: str, media_type: str = 'text/css') -> Response:
    version = asset_version(path)
    etag = f'"{version}"'
    cache = _IMMUTABLE if requested == version else _REVALIDATE
    headers = {'Cache-Control': cache, 'ETag': etag}
    if request.headers.get('if-none-match') == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=asset_bytes(path), media_type=media_type, headers=headers)
