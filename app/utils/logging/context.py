from __future__ import annotations

import contextlib
import contextvars
import functools
import uuid
from collections.abc import Awaitable, Callable, Iterator

# Per-request id (Plex-agent-kit style: a short hex tag for log isolation). The
# default keeps the log column aligned when no request scope is active.
_NO_REQUEST = '-----'
_request_id: contextvars.ContextVar[str] = contextvars.ContextVar('request_id', default=_NO_REQUEST)


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


def with_request_id[**P, R](fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Decorate an async entry point so all of its logs share one request id."""

    @functools.wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        with request_id_scope():
            return await fn(*args, **kwargs)

    return wrapper
