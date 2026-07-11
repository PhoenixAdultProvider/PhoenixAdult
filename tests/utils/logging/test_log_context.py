from __future__ import annotations

import logging

from app.utils.logging.context import SESSION_ID, current_request_id, request_id_scope
from app.utils.logging.logger import logger


def test_default_is_session_id_not_dashes():
    assert current_request_id() == SESSION_ID
    assert len(SESSION_ID) == 5 and SESSION_ID != '-----'


def test_scope_sets_and_resets_to_session():
    with request_id_scope('abc12') as rid:
        assert rid == 'abc12'
        assert current_request_id() == 'abc12'
    assert current_request_id() == SESSION_ID


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
    assert rec.request_id == 'zz999'
    assert rec.module == 'test_log_context'


def test_two_scopes_get_distinct_ids():
    ids = []
    for _ in range(2):
        with request_id_scope() as rid:
            ids.append(rid)
    assert ids[0] != ids[1]


def test_middleware_shares_id_across_endpoint_and_access_log():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.utils.logging.request_context import RequestContextMiddleware

    captured: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = captured.append  # type: ignore[method-assign]
    from app.utils.logging.context import HTTP

    base = logging.getLogger('phoenixadult')
    base.addHandler(handler)
    prior_level = base.level
    base.setLevel(HTTP)

    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get('/ping')
    async def ping() -> dict[str, bool]:
        logger.info('inside endpoint')
        return {'ok': True}

    try:
        TestClient(app).get('/ping')
    finally:
        base.removeHandler(handler)
        base.setLevel(prior_level)

    endpoint = [r.request_id for r in captured if 'inside endpoint' in r.getMessage()]
    access = [r.request_id for r in captured if '/ping' in r.getMessage()]
    assert endpoint and access
    assert endpoint[0] == access[0]
    assert endpoint[0] != SESSION_ID


def test_http_and_verbose_sit_below_debug() -> None:
    import logging

    from app.utils.logging.context import HTTP, VERBOSE
    from app.utils.logging.logger import _LEVEL_MAP

    assert VERBOSE < HTTP < logging.DEBUG
    assert not HTTP >= _LEVEL_MAP['info']
    assert not HTTP >= _LEVEL_MAP['debug']
    assert HTTP >= _LEVEL_MAP['http']
    assert HTTP >= _LEVEL_MAP['verbose']
