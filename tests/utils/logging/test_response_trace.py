from __future__ import annotations

import logging

import httpx
import pytest
import respx

from phoenixadult.utils.logging.context import VERBOSE


def _capture(records: list[logging.LogRecord]) -> logging.Handler:
    handler = logging.Handler()
    handler.emit = records.append  # type: ignore[method-assign]
    return handler


@pytest.fixture()
def verbose_records() -> list[logging.LogRecord]:
    from phoenixadult.utils.logging import logger as logger_module

    base = logging.getLogger('phoenixadult')
    records: list[logging.LogRecord] = []
    handler = _capture(records)
    previous = base.level
    logger_module.configure_logging(to_file=False)
    base.setLevel(VERBOSE)
    base.addHandler(handler)
    try:
        yield records
    finally:
        base.removeHandler(handler)
        base.setLevel(previous)


def _bodies(records: list[logging.LogRecord]) -> str:
    return '\n'.join(r.getMessage() for r in records if 'scrape-body' in r.getMessage())


@respx.mock
async def test_html_body_is_dumped_with_the_final_url(verbose_records: list[logging.LogRecord]) -> None:
    from phoenixadult.clients.base import Client, FetchCtx

    class _C(Client):
        pass

    respx.get('https://example.test/page').mock(return_value=httpx.Response(200, html='<h1>Marker Text</h1>'))
    await _C().fetch_and_load('https://example.test/page', FetchCtx())

    dumped = _bodies(verbose_records)
    assert 'GET https://example.test/page' in dumped
    assert '<h1>Marker Text</h1>' in dumped


@respx.mock
async def test_json_body_is_pretty_printed(verbose_records: list[logging.LogRecord]) -> None:
    from phoenixadult.clients.base import Client

    class _C(Client):
        pass

    respx.get('https://example.test/api').mock(return_value=httpx.Response(200, json={'b': 2, 'a': [1]}))
    await _C().fetch_json('https://example.test/api')

    dumped = _bodies(verbose_records)
    assert '"a": [\n' in dumped, 'json must be indented, not the raw one-line payload'
    assert dumped.index('"a"') < dumped.index('"b"'), 'keys are sorted so two dumps can be diffed'


@respx.mock
async def test_a_failed_page_is_dumped_too(verbose_records: list[logging.LogRecord]) -> None:
    from phoenixadult.clients.base import Client, FetchCtx

    class _C(Client):
        pass

    respx.get('https://example.test/blocked').mock(return_value=httpx.Response(403, html='<title>Just a moment...</title>'))
    assert await _C().fetch_and_load('https://example.test/blocked', FetchCtx()) is None

    assert 'Just a moment' in _bodies(verbose_records), 'the body of a refusal is the whole point of the dump'


@respx.mock
async def test_binary_responses_are_never_read(verbose_records: list[logging.LogRecord]) -> None:
    from phoenixadult.utils.http.client import make_http

    payload = b'\x89PNG\r\n\x1a\n' + b'\x00' * 4096
    respx.get('https://example.test/i.png').mock(return_value=httpx.Response(200, content=payload, headers={'content-type': 'image/png'}))

    chunks = 0
    async with make_http() as client, client.stream('GET', 'https://example.test/i.png') as resp:
        async for _ in resp.aiter_bytes():
            chunks += 1

    assert chunks, 'the image must still stream chunk by chunk'
    assert not _bodies(verbose_records), 'an image body must never be buffered into the log'


@respx.mock
async def test_the_cap_clips_and_says_so(verbose_records: list[logging.LogRecord], monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.clients.base import Client, FetchCtx

    class _C(Client):
        pass

    monkeypatch.setenv('LOG_BODY_MAX_CHARS', '40')
    respx.get('https://example.test/long').mock(return_value=httpx.Response(200, html='<p>' + 'x' * 500 + '</p>'))
    await _C().fetch_and_load('https://example.test/long', FetchCtx())

    dumped = _bodies(verbose_records)
    assert 'clipped' in dumped
    assert 'x' * 500 not in dumped


@respx.mock
async def test_nothing_is_dumped_below_verbose() -> None:
    from phoenixadult.clients.base import Client, FetchCtx

    class _C(Client):
        pass

    base = logging.getLogger('phoenixadult')
    records: list[logging.LogRecord] = []
    handler = _capture(records)
    previous = base.level
    base.setLevel(logging.INFO)
    base.addHandler(handler)
    try:
        respx.get('https://example.test/quiet').mock(return_value=httpx.Response(200, html='<h1>Secret</h1>'))
        await _C().fetch_and_load('https://example.test/quiet', FetchCtx())
    finally:
        base.removeHandler(handler)
        base.setLevel(previous)

    assert 'Secret' not in '\n'.join(r.getMessage() for r in records)


@respx.mock
async def test_the_dev_ui_sink_sees_bodies_without_verbose() -> None:
    from phoenixadult.clients.base import Client, FetchCtx
    from phoenixadult.utils.logging.response_trace import begin_body_capture

    class _C(Client):
        pass

    base = logging.getLogger('phoenixadult')
    previous = base.level
    base.setLevel(logging.INFO)
    respx.get('https://example.test/page').mock(return_value=httpx.Response(200, html='<h1>Marker</h1>'))
    bodies = begin_body_capture()
    try:
        await _C().fetch_and_load('https://example.test/page', FetchCtx())
    finally:
        entries = bodies.end()
        base.setLevel(previous)

    assert [e.label for e in entries] == ['GET https://example.test/page']
    assert '<h1>Marker</h1>' in entries[0].body


@respx.mock
async def test_the_log_and_the_sink_carry_the_same_bodies(verbose_records: list[logging.LogRecord]) -> None:
    from phoenixadult.clients.base import Client, FetchCtx
    from phoenixadult.utils.logging.response_trace import begin_body_capture

    class _C(Client):
        pass

    respx.get('https://example.test/ok').mock(return_value=httpx.Response(200, html='<h1>Kept</h1>'))
    respx.get('https://example.test/refused').mock(return_value=httpx.Response(403, html='<title>Just a moment...</title>'))
    respx.get('https://example.test/api').mock(return_value=httpx.Response(200, json={'b': 2, 'a': [1]}))

    bodies = begin_body_capture()
    try:
        await _C().fetch_and_load('https://example.test/ok', FetchCtx())
        await _C().fetch_and_load('https://example.test/refused', FetchCtx())
        await _C().fetch_json('https://example.test/api')
    finally:
        entries = bodies.end()

    dumped = _bodies(verbose_records)
    for entry in entries:
        assert entry.body in dumped, f'{entry.label} reached the dev UI but not the log'
    assert len(entries) == 3, 'a refusal and a json payload both belong in the dev UI, not just the page that worked'
    assert [e.content_type for e in entries] == ['html', 'html', 'json']


@respx.mock
async def test_a_page_with_no_content_type_is_still_dumped(verbose_records: list[logging.LogRecord]) -> None:
    from phoenixadult.clients.base import Client, FetchCtx

    class _C(Client):
        pass

    respx.get('https://example.test/bare').mock(return_value=httpx.Response(200, content=b'<h1>Unlabelled</h1>', headers={'content-type': ''}))
    await _C().fetch_and_load('https://example.test/bare', FetchCtx())

    assert 'Unlabelled' in _bodies(verbose_records), 'a server that omits content-type must not silence the dump'


@respx.mock
async def test_an_odd_text_type_is_still_dumped(verbose_records: list[logging.LogRecord]) -> None:
    from phoenixadult.clients.base import Client, FetchCtx

    class _C(Client):
        pass

    respx.get('https://example.test/odd').mock(return_value=httpx.Response(200, content=b'<h1>Odd</h1>', headers={'content-type': 'httpd/unix-directory'}))
    await _C().fetch_and_load('https://example.test/odd', FetchCtx())

    assert 'Odd' in _bodies(verbose_records), 'only known binary types are skipped, not everything unrecognised'


@respx.mock
async def test_unlabelled_json_is_still_pretty_printed(verbose_records: list[logging.LogRecord]) -> None:
    from phoenixadult.clients.base import Client

    class _C(Client):
        pass

    respx.get('https://example.test/bare.json').mock(return_value=httpx.Response(200, content=b'{"b":2,"a":[1]}', headers={'content-type': ''}))
    await _C().fetch_json('https://example.test/bare.json')

    assert _bodies(verbose_records).count('"a": [') == 1
    assert '"b": 2' in _bodies(verbose_records)


@respx.mock
async def test_an_oversized_body_is_skipped_by_declared_length(verbose_records: list[logging.LogRecord]) -> None:
    from phoenixadult.clients.base import Client, FetchCtx
    from phoenixadult.utils.logging.response_trace import MAX_TRACE_BYTES

    class _C(Client):
        pass

    respx.get('https://example.test/huge').mock(return_value=httpx.Response(200, content=b'x' * (MAX_TRACE_BYTES + 1), headers={'content-type': 'text/plain'}))
    await _C().fetch_and_load('https://example.test/huge', FetchCtx())

    assert not _bodies(verbose_records)


@respx.mock
async def test_the_scrape_path_traces_even_with_no_transport_hook(verbose_records: list[logging.LogRecord]) -> None:
    from phoenixadult.clients.base import Client, FetchCtx
    from phoenixadult.utils.http import client as client_mod

    class _C(Client):
        pass

    scraper = _C()
    scraper._http = client_mod.httpx2.AsyncClient(event_hooks={}, follow_redirects=True)
    respx.get('https://example.test/hooked-off').mock(return_value=httpx.Response(200, html='<h1>Still Dumped</h1>'))
    try:
        await scraper.fetch_and_load('https://example.test/hooked-off', FetchCtx())
    finally:
        await scraper._http.aclose()

    assert 'Still Dumped' in _bodies(verbose_records), 'the scrape path must not depend on the transport hook firing'


@respx.mock
async def test_a_body_is_never_dumped_twice(verbose_records: list[logging.LogRecord]) -> None:
    from phoenixadult.clients.base import Client, FetchCtx

    class _C(Client):
        pass

    respx.get('https://example.test/once').mock(return_value=httpx.Response(200, html='<h1>Once</h1>'))
    await _C().fetch_and_load('https://example.test/once', FetchCtx())

    assert _bodies(verbose_records).count('<h1>Once</h1>') == 1


def test_the_startup_banner_names_the_version() -> None:
    import phoenixadult
    from phoenixadult import app_factory

    base = logging.getLogger('phoenixadult')
    records: list[logging.LogRecord] = []
    handler = _capture(records)
    base.addHandler(handler)
    try:
        app_factory._log_startup_banner()
    finally:
        base.removeHandler(handler)

    assert any(phoenixadult.__version__ in r.getMessage() for r in records), 'the banner must say which build is running'
