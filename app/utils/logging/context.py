from __future__ import annotations

import contextlib
import contextvars
import logging
import os
import uuid
from collections.abc import Iterator

# Winston-style tail of the hierarchy: DEBUG(10) > HTTP(7) > VERBOSE(5), so access
# lines only appear at LOG_LEVEL=http or verbose — never at the info/debug defaults.
HTTP = 7
logging.addLevelName(HTTP, 'HTTP')
VERBOSE = 5
logging.addLevelName(VERBOSE, 'VERBOSE')

SESSION_ID = uuid.uuid4().hex[:5]

_LOG_FORMAT = '%(asctime)s  (%(request_id)s) %(levelfield)s %(locfield)s: %(message)s'
_LEVEL_NAME_WIDTH = 8  # widest level name, "CRITICAL"
_LOCATION_WIDTH = 28  # widest "module:line" content


class AlignedFormatter(logging.Formatter):
    """Provider log format with fixed-width level + location fields so the message
    colon aligns. Defaults request_id (the record factory isn't installed in the
    uvicorn reloader process)."""

    def __init__(self, fmt: str = _LOG_FORMAT, **kwargs: object) -> None:
        super().__init__(fmt, **kwargs)  # type: ignore[arg-type]

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, 'request_id'):
            record.request_id = SESSION_ID
        record.levelfield = f'{record.levelname:<{_LEVEL_NAME_WIDTH}}'
        module = record.module
        if module == '__init__':  # disambiguate package __init__.py by its folder
            folder = os.path.basename(os.path.dirname(record.pathname))
            if folder:
                module = f'{folder}/{module}'
        location = f'{module}:{record.lineno}'
        record.locfield = f'{location:<{_LOCATION_WIDTH}}'
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
