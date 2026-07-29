from __future__ import annotations

import contextlib
import contextvars
import logging
import os
import uuid
from collections.abc import Iterator

HTTP = 7
logging.addLevelName(HTTP, 'HTTP')
VERBOSE = 5
logging.addLevelName(VERBOSE, 'VERBOSE')

SESSION_ID = uuid.uuid4().hex[:5]

_LOG_FORMAT = '%(asctime)s  (%(request_id)s) %(levelfield)s %(locfield)s: %(message)s'
_LEVEL_NAME_WIDTH = 8
_LOCATION_WIDTH = 28


class AlignedFormatter(logging.Formatter):
    def __init__(self, fmt: str = _LOG_FORMAT, **kwargs: object) -> None:
        super().__init__(fmt, **kwargs)  # type: ignore[arg-type]

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, 'request_id'):
            record.request_id = SESSION_ID
        record.levelfield = f'{record.levelname:<{_LEVEL_NAME_WIDTH}}'
        module = record.module
        if module == '__init__':
            folder = os.path.basename(os.path.dirname(record.pathname))
            if folder:
                module = f'{folder}/{module}'
        location = f'{module}:{record.lineno}'
        record.locfield = f'{location:<{_LOCATION_WIDTH}}'
        return super().format(record)


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


_scrape_phase: contextvars.ContextVar[str] = contextvars.ContextVar('scrape_phase', default='')


def current_scrape_phase() -> str:
    return _scrape_phase.get()


@contextlib.contextmanager
def scrape_phase_scope(phase: str) -> Iterator[None]:
    token = _scrape_phase.set(phase)
    try:
        yield
    finally:
        _scrape_phase.reset(token)
