from __future__ import annotations

import contextlib
import contextvars
import logging
import uuid
from collections.abc import Iterator

# Dedicated HTTP level (between INFO and WARNING) so request lines tag as [HTTP] and
# still show at the default info threshold. Registered here so the name resolves
# wherever AlignedFormatter is used.
HTTP = 25
logging.addLevelName(HTTP, 'HTTP')

# A short hex id for this process run — the default for logs not tied to an
# external request (startup, lifespan, uvicorn server lines). Changes on restart.
SESSION_ID = uuid.uuid4().hex[:5]

# Shared log layout, padded so the ":" before the message lands at a fixed column:
#   "<ts>  (<id>) <[LEVEL] padded> <(module:line) padded>: message"
_LOG_FORMAT = '%(asctime)s  (%(request_id)s) %(levelfield)s %(locfield)s: %(message)s'
_LEVEL_NAME_WIDTH = 8  # widest level name, "CRITICAL" — name is left-padded inside the brackets
_LOCATION_WIDTH = 30  # widest module (~24) + ":line" + parens


class AlignedFormatter(logging.Formatter):
    """Provider log format with fixed-width level + location fields so the message
    colon aligns. Defaults request_id (the record factory isn't installed in the
    uvicorn reloader process)."""

    def __init__(self, fmt: str = _LOG_FORMAT, **kwargs: object) -> None:
        super().__init__(fmt, **kwargs)  # type: ignore[arg-type]

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, 'request_id'):
            record.request_id = SESSION_ID
        record.levelfield = f'[{record.levelname:<{_LEVEL_NAME_WIDTH}}]'
        record.locfield = f'({record.module}:{record.lineno})'.ljust(_LOCATION_WIDTH)
        return super().format(record)

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
