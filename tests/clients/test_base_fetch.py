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
    assert await client.fetch_and_load('https://x.test/ok') is not None
    assert await client.fetch_and_load('https://x.test/blocked') is None
    assert await client.fetch_and_load('https://x.test/empty') is None


def test_group_genre_for_scale() -> None:
    c = _C()
    assert c.group_genre_for(0) is None
    assert c.group_genre_for(1) is None
    assert c.group_genre_for(2) is None
    assert c.group_genre_for(3) == 'Threesome'
    assert c.group_genre_for(4) == 'Foursome'
    assert c.group_genre_for(5) == 'Orgy'
    assert c.group_genre_for(9) == 'Orgy'


@respx.mock
async def test_resolve_actor_photos_dedups_extracts_and_preserves_order() -> None:
    respx.get('https://x.test/a').mock(return_value=httpx.Response(200, text='<html><img id="p" src="https://cdn/a.jpg"></html>'))
    respx.get('https://x.test/b').mock(return_value=httpx.Response(200, text='<html><img id="p" src="https://cdn/b.jpg"></html>'))
    refs = [('Alice', 'https://x.test/a'), ('Bob', 'https://x.test/b'), ('Alice', 'https://x.test/a'), ('Cara', '')]
    actors = await _C().resolve_actor_photos(refs, lambda sel: sel.xpath('//img[@id="p"]/@src').get() or '')
    assert [a.name for a in actors] == ['Alice', 'Bob', 'Cara']
    assert actors[0].photo_url == 'https://cdn/a.jpg'
    assert actors[1].photo_url == 'https://cdn/b.jpg'
    assert actors[2].photo_url == ''
