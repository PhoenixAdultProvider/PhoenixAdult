from __future__ import annotations

import contextlib
import contextvars
import uuid
from collections.abc import Iterator

# Shared log layout: "<ts>  (<id>) [LEVEL] (module:lineno): message".
LOG_FORMAT = '%(asctime)s  (%(request_id)s) [%(levelname)s] (%(module)s:%(lineno)d): %(message)s'

# A short hex id for this process run — the default for logs not tied to an
# external request (startup, lifespan, uvicorn server lines). Changes on restart.
SESSION_ID = uuid.uuid4().hex[:5]

# Per-request id (Plex-agent-kit style) — overrides SESSION_ID for the duration
# of one HTTP request so its logs (match/metadata + scrapers + access line) share it.
_request_id: contextvars.ContextVar[str] = contextvars.ContextVar('request_id', default=SESSION_ID)


def current_request_id() -> str:
    return _request_id.get()


def new_request_id() -> str:
    return uuid.uuid4().hex[:5]


@contextlib.contextmanager
def request_id_scope(value: str | None = None) -> Iterator[str]:
    rid = value or new_request_id()
    token = _request_id.set(rid)
    try:
        yield rid
    finally:
        _request_id.reset(token)
