from __future__ import annotations

import json

import httpx
import respx

from phoenixadult.utils.captcha import pow as pow_module
from phoenixadult.utils.captcha.pow import get_verified_cookies, solve_pow

_DIFFICULTY = 4


def _challenge_page(return_to: str) -> str:
    config = {'challenge': 'test-challenge', 'difficulty': _DIFFICULTY, 'timestamp': 1234567890, 'returnTo': return_to}
    return f'<html><script>var turnstileConfig = {json.dumps(config)};</script></html>'


def test_solve_pow_finds_a_nonce_below_the_target() -> None:
    nonce = solve_pow('test-challenge', _DIFFICULTY)
    import hashlib

    digest = hashlib.sha256(f'test-challenge:{nonce}'.encode()).digest()
    assert int.from_bytes(digest, 'big') < 1 << (256 - _DIFFICULTY)


@respx.mock
async def test_a_www_site_whose_challenge_lives_on_the_apex_still_solves() -> None:
    gallery = 'https://www.challenge-hop.test/video/gallery'
    apex_challenge = 'https://challenge-hop.test/turnstile/challenge?r=%2Fvideo%2Fgallery'
    respx.get(gallery).mock(return_value=httpx.Response(301, headers={'location': '//challenge-hop.test/turnstile/challenge?r=%2Fvideo%2Fgallery'}))
    respx.get(apex_challenge).mock(return_value=httpx.Response(200, text=_challenge_page('/video/gallery'), headers={'set-cookie': 'SRV=abc; path=/'}))
    verify = respx.post('https://challenge-hop.test/turnstile/verify').mock(
        return_value=httpx.Response(200, json={'success': True}, headers={'set-cookie': 'pow_token=solved; path=/'})
    )

    cookies = await get_verified_cookies('https://www.challenge-hop.test', '/video/gallery')
    assert cookies is not None and cookies.get('pow_token') == 'solved', 'the apex-hosted challenge must be solved, not skipped'
    assert verify.called, 'the verify must be posted to the challenge host, not the www alias'


@respx.mock
async def test_a_same_host_challenge_still_solves() -> None:
    gallery = 'https://same-host.test/video/gallery'
    respx.get(gallery).mock(return_value=httpx.Response(301, headers={'location': '/turnstile/challenge?r=%2Fvideo%2Fgallery'}))
    respx.get('https://same-host.test/turnstile/challenge?r=%2Fvideo%2Fgallery').mock(return_value=httpx.Response(200, text=_challenge_page('/video/gallery')))
    respx.post('https://same-host.test/turnstile/verify').mock(
        return_value=httpx.Response(200, json={'success': True}, headers={'set-cookie': 'pow_token=ok; path=/'})
    )

    cookies = await get_verified_cookies('https://same-host.test', '/video/gallery')
    assert cookies is not None and cookies.get('pow_token') == 'ok'


@respx.mock
async def test_a_redirect_to_a_foreign_domain_is_never_followed() -> None:
    gallery = 'https://victim-site.test/video/gallery'
    respx.get(gallery).mock(return_value=httpx.Response(301, headers={'location': 'https://evil-elsewhere.test/turnstile/challenge'}))

    cookies = await get_verified_cookies('https://victim-site.test', '/video/gallery')
    assert cookies == {}, 'a cross-domain redirect must stop the chain, yielding only the cookies gathered so far'
    assert pow_module._same_site('evil-elsewhere.test', 'victim-site.test') is False


def test_same_site_pairs() -> None:
    assert pow_module._same_site('www.caughtmycoach.com', 'caughtmycoach.com')
    assert pow_module._same_site('caughtmycoach.com', 'www.caughtmycoach.com')
    assert pow_module._same_site('CAUGHTMYCOACH.COM', 'www.caughtmycoach.com')
    assert not pow_module._same_site('caughtmycoach.com', 'cheatingsis.com')
    assert not pow_module._same_site('wwwcaughtmycoach.com', 'caughtmycoach.com')
