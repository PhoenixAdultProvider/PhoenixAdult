from __future__ import annotations

import re

from phoenixadult.utils.auth.url_signing import sign_url, strip_sig

SIG_SUFFIX = re.compile(r'[?&]sig=[0-9a-f]{32}$')


def test_signing_is_always_on() -> None:
    signed = sign_url('/cache/a/images/i.jpg')
    assert signed is not None and SIG_SUFFIX.search(signed)


def test_sign_url_appends_a_sig() -> None:
    signed = sign_url('http://x/cache/a/images/i.jpg')
    assert signed is not None and SIG_SUFFIX.search(signed)
    assert signed.startswith('http://x/cache/a/images/i.jpg?sig=')
    with_query = sign_url('/images/proxy?url=http%3A%2F%2Fu%2Fp.jpg')
    assert with_query is not None and '&sig=' in with_query


def test_sign_url_is_idempotent_and_strip_undoes_it() -> None:
    signed = sign_url('/images/local/people/actor.jane_female.jpg?v=abc123')
    assert signed == sign_url(signed)
    assert strip_sig(signed or '') == '/images/local/people/actor.jane_female.jpg?v=abc123'


def test_signature_ignores_the_host() -> None:
    a = sign_url('http://lan.host:3000/cache/a/images/i.jpg') or ''
    b = sign_url('https://tunnel.example/cache/a/images/i.jpg') or ''
    assert a.rsplit('sig=', 1)[-1] == b.rsplit('sig=', 1)[-1]
