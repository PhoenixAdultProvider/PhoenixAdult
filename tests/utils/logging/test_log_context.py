from __future__ import annotations

import logging

from app.utils.logging.context import current_request_id, request_id_scope, with_request_id
from app.utils.logging.logger import logger


def test_default_request_id_outside_scope():
    assert current_request_id() == '-----'


def test_scope_sets_and_resets():
    with request_id_scope('abc12') as rid:
        assert rid == 'abc12'
        assert current_request_id() == 'abc12'
    assert current_request_id() == '-----'


async def test_decorator_generates_5char_id_and_resets():
    seen = {}

    @with_request_id
    async def op() -> None:
        seen['id'] = current_request_id()

    await op()
    assert len(seen['id']) == 5 and seen['id'] != '-----'
    assert current_request_id() == '-----'  # reset after the call


def test_record_carries_request_id_and_real_caller():
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append  # type: ignore[method-assign]
    base = logging.getLogger('phoenixadult')
    base.addHandler(handler)
    try:
        with request_id_scope('zz999'):
            logger.info('hello world')
    finally:
        base.removeHandler(handler)

    rec = records[-1]
    assert rec.request_id == 'zz999'  # stamped by the factory
    # stacklevel must resolve module/lineno to THIS test file, not logger.py.
    assert rec.module == 'test_log_context'


def test_two_requests_get_distinct_ids():
    ids = []
    for _ in range(2):
        with request_id_scope() as rid:
            ids.append(rid)
    assert ids[0] != ids[1]
