from __future__ import annotations

import pytest

from phoenixadult.utils.http import ssrf_guard


async def test_a_name_that_resolves_to_a_private_address_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    async def resolves_internal(host: str) -> list[str]:
        return ['10.1.2.3']

    monkeypatch.setattr(ssrf_guard, '_resolve', resolves_internal)
    monkeypatch.setattr(ssrf_guard, '_proxied', lambda: False)
    with pytest.raises(ValueError, match='private address'):
        await ssrf_guard.guard_target('http://metadata.attacker.test/latest')


async def test_a_public_name_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    async def resolves_public(host: str) -> list[str]:
        return ['93.184.216.34']

    monkeypatch.setattr(ssrf_guard, '_resolve', resolves_public)
    monkeypatch.setattr(ssrf_guard, '_proxied', lambda: False)
    await ssrf_guard.guard_target('https://example.test/x.png')


async def test_an_unresolvable_name_is_not_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    async def refuses(host: str) -> list[str]:
        raise RuntimeError('dns down')

    monkeypatch.setattr(ssrf_guard, '_resolve', refuses)
    monkeypatch.setattr(ssrf_guard, '_proxied', lambda: False)
    await ssrf_guard.guard_target('https://unresolvable.test/x.png')


async def test_a_proxy_owns_egress_so_we_do_not_resolve(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []

    async def should_not_run(host: str) -> list[str]:
        called.append(host)
        return []

    monkeypatch.setattr(ssrf_guard, '_resolve', should_not_run)
    monkeypatch.setattr(ssrf_guard, '_proxied', lambda: True)
    await ssrf_guard.guard_target('https://only-the-proxy-knows.test/x.png')
    assert called == [], 'resolving locally would refuse hosts only the proxy can reach'


async def test_literal_private_addresses_never_need_dns() -> None:
    for url in ('http://127.0.0.1:6379/', 'http://10.0.0.1/x', 'http://nas.local/x'):
        with pytest.raises(ValueError, match='blocked host'):
            await ssrf_guard.guard_target(url)


async def test_non_http_schemes_are_refused() -> None:
    with pytest.raises(ValueError, match='invalid url'):
        await ssrf_guard.guard_target('file:///etc/passwd')


async def test_the_impersonate_bypass_refuses_an_internal_target(monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.utils.http import impersonate

    monkeypatch.setattr(impersonate.impersonate_backend, 'is_available', lambda: True)
    assert await impersonate.impersonate_get_bytes('http://127.0.0.1:6379/x.png') is None


async def test_the_people_download_refuses_an_internal_target() -> None:
    from phoenixadult.utils.people.cache import _download_image

    assert await _download_image('http://10.0.0.1/headshot.jpg', None) is None
