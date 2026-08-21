from __future__ import annotations

import pytest
from starlette.datastructures import Headers
from starlette.requests import Request

from phoenixadult.utils.auth import image_guard as ig


def _request(headers: dict[str, str], path: str = '/images/proxy') -> Request:
    scope = {
        'type': 'http',
        'method': 'GET',
        'path': path,
        'raw_path': path.encode(),
        'query_string': b'',
        'headers': Headers(headers).raw,
        'client': ('203.0.113.5', 1234),
        'scheme': 'http',
        'server': ('provider.test', 80),
        'root_path': '',
        'app': None,
    }
    return Request(scope)


async def test_a_bare_request_is_admitted_by_nothing() -> None:
    assert await ig._admitted_by(_request({'user-agent': 'curl/8'})) is None


async def test_plex_is_admitted_by_its_user_agent() -> None:
    assert await ig._admitted_by(_request({'user-agent': 'PlexMediaServer/1.40'})) == 'plex user-agent'


async def test_an_image_fetcher_is_admitted_by_the_accept_header() -> None:
    assert await ig._admitted_by(_request({'user-agent': 'x', 'accept': 'image/png'})) == 'image subresource'


async def test_the_guard_stays_open_while_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ig.env.__class__, 'image_guard_enabled', property(lambda self: False))
    await ig.image_guard(_request({'user-agent': 'curl/8'}))


async def test_the_guard_denies_once_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ig.env.__class__, 'image_guard_enabled', property(lambda self: True))
    with pytest.raises(ig.ImageAccessDenied):
        await ig.image_guard(_request({'user-agent': 'curl/8'}))


async def test_a_bare_client_would_be_denied_if_the_guard_were_on() -> None:
    assert await ig._admitted_by(_request({})) is None
    assert await ig._admitted_by(_request({'user-agent': 'curl/8', 'accept': '*/*'})) is None


@pytest.mark.parametrize(
    ('headers', 'why'),
    [
        ({'user-agent': 'PlexMediaServer/1.40'}, 'plex user-agent'),
        ({'user-agent': 'Plex/Cloud', 'accept': 'image/webp,image/*'}, 'image subresource'),
        ({'user-agent': 'Mozilla/5.0', 'accept': 'image/png', 'sec-fetch-site': 'same-origin', 'sec-fetch-mode': 'no-cors'}, 'same-origin subresource'),
    ],
)
async def test_the_consumers_we_serve_are_still_admitted(headers: dict[str, str], why: str) -> None:
    assert await ig._admitted_by(_request(headers)) == why


async def test_a_typed_in_url_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    navigation = {'user-agent': 'Mozilla/5.0', 'accept': 'text/html,image/webp', 'sec-fetch-mode': 'navigate', 'sec-fetch-site': 'none'}
    assert await ig._admitted_by(_request(navigation)) is None
