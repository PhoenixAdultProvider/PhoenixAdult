from __future__ import annotations

import httpx
import httpx2
import pytest
import respx

from phoenixadult.clients import get_client
from phoenixadult.clients.aggregators.data18 import Data18Client
from phoenixadult.clients.base import Client
from phoenixadult.clients.networks import blurredmedia
from phoenixadult.registry import find_site
from phoenixadult.utils.helpers.javbus_images import fetch_javbus_images


@pytest.mark.parametrize(
    ('scraper_type', 'expected'),
    [
        ('data18', 'data_user_captcha=1'),
        ('data18empire', 'ageConfirmed=true'),
        ('javbus', 'existmag=all'),
        ('couplescinema', 'WarningModal=true'),
        ('gasm', 'WarningModal=true'),
        ('karups', 'warningHidden=hide'),
        ('kellymadison', 'nats=MC4wLjMuNTguMC4wLjAuMC4w'),
        ('kink', 'viewing-preferences=straight%2Cgay'),
        ('5kporn', 'ageConfirmed=true'),
        ('scoregroup', 'tsg_verified=true'),
    ],
)
@respx.mock
async def test_site_cookies_survive_a_redirect_that_sets_a_cookie(scraper_type: str, expected: str) -> None:
    seen: list[str] = []
    respx.get('https://site.test/start').mock(return_value=httpx.Response(302, headers={'Location': 'https://site.test/end', 'Set-Cookie': 'sess=1; path=/'}))
    respx.get('https://site.test/end').mock(side_effect=lambda request: seen.append(request.headers.get('cookie', '')) or httpx.Response(200, text='ok'))
    client: Client | None = Data18Client() if scraper_type == 'data18' else get_client(scraper_type)
    assert client is not None
    await client.http.get('https://site.test/start')
    assert expected in seen[0] and 'sess=1' in seen[0]


@respx.mock
async def test_javbus_cookies_survive_a_redirect() -> None:
    seen: list[str] = []
    respx.get('https://www.javbus.com/en/ABC-123').mock(
        return_value=httpx.Response(302, headers={'Location': 'https://www.javbus.com/en/ABC-123/', 'Set-Cookie': 'sess=1; path=/'})
    )
    respx.get('https://www.javbus.com/en/ABC-123/').mock(
        side_effect=lambda request: seen.append(request.headers.get('cookie', '')) or httpx.Response(200, text='<html></html>')
    )
    async with httpx2.AsyncClient(follow_redirects=True) as http:
        await fetch_javbus_images(http, 'ABC-123')
    assert 'existmag=all' in seen[0] and 'sess=1' in seen[0]


async def test_a_blurredmedia_session_cookie_lands_in_the_jar(monkeypatch: pytest.MonkeyPatch) -> None:
    site = find_site('Hot Guys Fuck')
    assert site is not None

    async def jar(base_url: str) -> dict[str, str]:
        return {'SPSI': 'abc'}

    monkeypatch.setattr(blurredmedia, 'get_site_cookies', jar)
    client = blurredmedia.BlurredMediaClient()
    assert await client._session_cookie(site) == 'SPSI=abc'
    assert client.http.cookies.get('SPSI') == 'abc'
