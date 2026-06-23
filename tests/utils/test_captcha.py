from __future__ import annotations

import hashlib

import httpx
import respx

from app.utils.captcha.pow import get_verified_cookies, solve_pow


def test_solve_pow_meets_target() -> None:
    nonce = solve_pow('chal', 8)
    digest = hashlib.sha256(f'chal:{nonce}'.encode()).digest()
    assert int.from_bytes(digest, 'big') < (1 << (256 - 8))


@respx.mock
async def test_get_verified_cookies_no_challenge() -> None:
    respx.get('https://nochal.example/video/gallery').mock(
        return_value=httpx.Response(200, text='<html>no challenge here</html>', headers={'set-cookie': 'sess=1; Path=/'})
    )
    cookies = await get_verified_cookies('https://nochal.example')
    assert cookies == {'sess': '1'}


@respx.mock
async def test_get_verified_cookies_rate_limited() -> None:
    respx.get('https://limited.example/video/gallery').mock(return_value=httpx.Response(429))
    assert await get_verified_cookies('https://limited.example') is None
