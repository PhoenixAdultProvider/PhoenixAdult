from __future__ import annotations

import logging

import httpx2
import pytest

from phoenixadult.utils.http.client import _log_request
from phoenixadult.utils.logging.context import HTTP, current_scrape_phase, scrape_phase_scope


def _request(method: str, url: str) -> httpx2.Request:
    return httpx2.Request(method, url)


async def test_requests_stay_at_http_level_outside_a_scrape(caplog: pytest.LogCaptureFixture) -> None:
    assert current_scrape_phase() == ''
    with caplog.at_level(HTTP, logger='phoenixadult'):
        await _log_request(_request('GET', 'https://example.com/quiet'))

    assert [r.levelno for r in caplog.records] == [HTTP]


async def test_every_search_url_is_logged_at_info_with_its_method(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger='phoenixadult'), scrape_phase_scope('search TeamSkeet'):
        await _log_request(_request('GET', 'https://www.teamskeet.com/movies/repeat-offence'))
        await _log_request(_request('POST', 'https://www.teamskeet.com/api/search?q=a+b'))

    assert [r.levelno for r in caplog.records] == [logging.INFO, logging.INFO]
    assert caplog.records[0].getMessage() == '[search TeamSkeet] Requesting GET "https://www.teamskeet.com/movies/repeat-offence"'
    assert caplog.records[1].getMessage() == '[search TeamSkeet] Requesting POST "https://www.teamskeet.com/api/search?q=a+b"'


async def test_update_logs_every_supporting_url_too(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger='phoenixadult'), scrape_phase_scope('update TeamSkeet'):
        await _log_request(_request('GET', 'https://www.teamskeet.com/movies/a-scene'))
        await _log_request(_request('GET', 'https://www.teamskeet.com/models/m1'))

    messages = [r.getMessage() for r in caplog.records]
    assert messages == [
        '[update TeamSkeet] Requesting GET "https://www.teamskeet.com/movies/a-scene"',
        '[update TeamSkeet] Requesting GET "https://www.teamskeet.com/models/m1"',
    ]


async def test_the_phase_is_restored_when_the_scrape_ends(caplog: pytest.LogCaptureFixture) -> None:
    with scrape_phase_scope('search Vixen'):
        assert current_scrape_phase() == 'search Vixen'
    assert current_scrape_phase() == ''

    with caplog.at_level(HTTP, logger='phoenixadult'):
        await _log_request(_request('GET', 'https://example.com/after'))
    assert [r.levelno for r in caplog.records] == [HTTP]
