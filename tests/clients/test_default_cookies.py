from __future__ import annotations

import httpx
import pytest
import respx

from phoenixadult.clients import get_client
from phoenixadult.clients.aggregators.data18 import Data18Client
from phoenixadult.clients.base import Client


@pytest.mark.parametrize(
    ('scraper_type', 'expected'),
    [
        ('data18', 'data_user_captcha=1'),
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
