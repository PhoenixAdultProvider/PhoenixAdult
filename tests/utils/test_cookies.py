from __future__ import annotations

import httpx
import httpx2
import respx

from phoenixadult.utils.cookies.site_cookies import get_site_cookies


@respx.mock
async def test_get_site_cookies() -> None:
    respx.get('https://cookies.example/').mock(return_value=httpx.Response(200, headers={'set-cookie': 'sid=xyz; Path=/'}))
    cookies = await get_site_cookies('https://cookies.example/')
    assert cookies == {'sid': 'xyz'}


@respx.mock
async def test_get_site_cookies_failure_returns_empty() -> None:
    respx.get('https://down.example/').mock(side_effect=httpx2.ConnectError('boom'))
    assert await get_site_cookies('https://down.example/') == {}
