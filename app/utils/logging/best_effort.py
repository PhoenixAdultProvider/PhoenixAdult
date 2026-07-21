from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from app.utils.logging.logger import logger


@contextmanager
def best_effort(scope: str, action: str, *, level: str = 'warn') -> Iterator[None]:
    """Run a block whose failure must not abort the caller: swallow any Exception and log it as
    '<action> failed: <err>' at `level` (default warn). BaseException still propagates."""
    try:
        yield
    except Exception as err:  # noqa: BLE001 - swallowing is the whole point
        getattr(logger, level)(scope, f'{action} failed: {err}')
