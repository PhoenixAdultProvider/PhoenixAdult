from __future__ import annotations

import httpx
import httpx2
import respx

from app.utils.helpers.javbus_images import fetch_javbus_images

_HTML = (
    '<html>'
    '<a href="/cover/abc_b.jpg">cover</a>'
    '<a class="sample-box" href="https://img.example/sample1.jpg">s1</a>'
    '<a class="sample-box" href="https://img.example/nowprinting.jpg">skip</a>'
    '</html>'
)


@respx.mock
async def test_fetch_javbus_images() -> None:
    respx.route(method='GET', url__regex=r'javbus\.com/en/').mock(return_value=httpx.Response(200, text=_HTML))
    async with httpx2.AsyncClient() as client:
        imgs = await fetch_javbus_images(client, 'ABC-123')
    assert 'https://www.javbus.com/cover/abc_b.jpg' in imgs
    assert 'https://img.example/sample1.jpg' in imgs
    assert all('nowprinting' not in u for u in imgs)


@respx.mock
async def test_fetch_javbus_images_404() -> None:
    respx.route(method='GET', url__regex=r'javbus\.com/en/').mock(return_value=httpx.Response(200, text='<html>404 Page Not Found</html>'))
    async with httpx2.AsyncClient() as client:
        assert await fetch_javbus_images(client, 'ZZZ-999') == []
