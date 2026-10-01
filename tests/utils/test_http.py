from __future__ import annotations

import httpx
import pytest
import respx

from phoenixadult.utils.http.client import make_http, read_capped
from phoenixadult.utils.http.ssrf_guard import is_blocked_hostname, is_private_address


def test_ssrf_guard_blocks_private() -> None:
    assert is_private_address('127.0.0.1')
    assert is_private_address('169.254.169.254')
    assert is_private_address('10.0.0.1')
    assert not is_private_address('8.8.8.8')


def test_ssrf_guard_blocks_hostnames() -> None:
    assert is_blocked_hostname('localhost')
    assert not is_blocked_hostname('example.com')


@respx.mock
async def test_make_http_blocks_a_redirect_to_an_internal_host() -> None:
    respx.get('https://evil.test/r').mock(return_value=httpx.Response(302, headers={'location': 'http://127.0.0.1:6379/'}))
    async with make_http() as client:
        with pytest.raises(ValueError, match='blocked redirect'):
            await client.get('https://evil.test/r')


@respx.mock
async def test_make_http_follows_a_public_redirect() -> None:
    respx.get('https://a.test/r').mock(return_value=httpx.Response(302, headers={'location': 'https://b.test/final'}))
    respx.get('https://b.test/final').mock(return_value=httpx.Response(200, text='ok'))
    async with make_http() as client:
        r = await client.get('https://a.test/r')
    assert r.status_code == 200 and r.text == 'ok'


@respx.mock
async def test_read_capped_refuses_an_oversized_body() -> None:
    respx.get('https://cdn.test/big').mock(return_value=httpx.Response(200, content=b'x' * 100))
    async with make_http() as client, client.stream('GET', 'https://cdn.test/big') as resp:
        with pytest.raises(ValueError, match='exceeds 10 bytes'):
            await read_capped(resp, 10)


@respx.mock
async def test_read_capped_can_keep_just_the_head() -> None:
    respx.get('https://cdn.test/big').mock(return_value=httpx.Response(200, content=b'abcdefghij' * 10))
    async with make_http() as client, client.stream('GET', 'https://cdn.test/big') as resp:
        assert await read_capped(resp, 4, truncate=True) == b'abcd'
