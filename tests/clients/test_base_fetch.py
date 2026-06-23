"""Base Client fetch_and_load: 202 / empty-body responses are anti-bot soft-blocks
and must be treated as failures (so the bypass fallback can fire)."""

from __future__ import annotations

import httpx
import respx

from app.clients.base import Client


class _C(Client):
    pass


@respx.mock
async def test_202_and_empty_body_are_not_ok() -> None:
    respx.get('https://x.test/ok').mock(return_value=httpx.Response(200, text='<html>hi</html>'))
    respx.get('https://x.test/blocked').mock(return_value=httpx.Response(202, text=''))
    respx.get('https://x.test/empty').mock(return_value=httpx.Response(200, text='   '))

    client = _C()
    assert await client.fetch_and_load('https://x.test/ok') is not None  # real page
    assert await client.fetch_and_load('https://x.test/blocked') is None  # 202 soft-block
    assert await client.fetch_and_load('https://x.test/empty') is None  # empty 2xx
