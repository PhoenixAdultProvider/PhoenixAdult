from __future__ import annotations

import logging

from phoenixadult.utils.logging.logger import logger


def _capture(records: list[logging.LogRecord]) -> logging.Handler:
    handler = logging.Handler()
    handler.emit = records.append  # type: ignore[method-assign]
    return handler


def test_error_exc_info_carries_the_traceback() -> None:
    base = logging.getLogger('phoenixadult')
    records: list[logging.LogRecord] = []
    handler = _capture(records)
    base.addHandler(handler)
    try:
        try:
            raise ValueError('boom')
        except ValueError:
            logger.error('tag', 'failed', exc_info=True)
    finally:
        base.removeHandler(handler)
    rec = records[-1]
    assert rec.exc_info is not None
    assert 'boom' in logging.Formatter().format(rec)
    assert 'exc_info' not in rec.getMessage()


def test_meta_still_serialized_without_exc_info() -> None:
    base = logging.getLogger('phoenixadult')
    records: list[logging.LogRecord] = []
    handler = _capture(records)
    base.addHandler(handler)
    try:
        logger.error('tag', 'failed', site='X')
    finally:
        base.removeHandler(handler)
    rec = records[-1]
    assert rec.exc_info is None
    assert '"site": "X"' in rec.getMessage()
