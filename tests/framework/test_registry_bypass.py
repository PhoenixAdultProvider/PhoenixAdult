from __future__ import annotations

import dataclasses
from typing import get_args

import httpx
import pytest
import respx

from phoenixadult import registry
from phoenixadult.clients.base import Client
from phoenixadult.models.site_info import BypassName
from phoenixadult.utils.http import bypass
from phoenixadult.utils.http.bypass_types import BypassRequest, BypassResponse
from scripts.generate_sitelist import bypass_label


def test_every_declared_backend_exists() -> None:
    known = {backend.name for backend in bypass.ALL_BACKENDS}
    assert set(get_args(BypassName)) == known
    declared = {name for site in registry.SITE_DEFINITIONS for name in site.bypass}
    assert declared <= known


def test_sites_on_one_host_must_agree() -> None:
    site = next(s for s in registry.SITE_DEFINITIONS if s.bypass)
    other = dataclasses.replace(site, name='Twin', bypass=('FlareSolverr',))
    with pytest.raises(RuntimeError, match='different PROVIDER_BYPASS'):
        registry._bypass_hosts([site, other])


def test_urls_resolve_to_their_registry_bypass() -> None:
    assert bypass.site_backends('https://www.iafd.com/title.rme/id=x') == ('Impersonate',)
    assert bypass.site_backends('https://scoreland.com/x') == ('Impersonate', 'FlareSolverr')
    assert bypass.site_backends('https://www.data18.com/scenes/1') == ()


async def test_a_required_site_tries_only_its_listed_backends_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    tried: list[str] = []
    for backend in bypass.ALL_BACKENDS:

        async def refuse(req: BypassRequest, name: str = backend.name) -> BypassResponse | None:
            tried.append(name)
            return None

        monkeypatch.setattr(backend, 'is_available', lambda: True)
        monkeypatch.setattr(backend, 'request', refuse)

    await bypass.bypass_get('https://www.scoreland.com/big-boob-videos/')
    assert tried == ['Impersonate', 'FlareSolverr']


class _Plain(Client):
    pass


@respx.mock
async def test_fetch_skips_the_plain_request_only_where_the_registry_requires_it(monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.utils.http.impersonate import impersonate_backend

    required = respx.get('https://www.iafd.com/x').mock(return_value=httpx.Response(200, text='<p>plain</p>'))
    plain = respx.get('https://www.data18.com/x').mock(return_value=httpx.Response(200, text='<p>plain</p>'))

    async def impersonated(req: BypassRequest) -> BypassResponse:
        return BypassResponse(status=200, body='<p>impersonated</p>')

    monkeypatch.setattr(impersonate_backend, 'request', impersonated)
    client = _Plain()
    got = await client.fetch_and_load('https://www.iafd.com/x')
    assert got is not None and 'impersonated' in got['html'] and not required.called
    got = await client.fetch_and_load('https://www.data18.com/x')
    assert got is not None and 'plain' in got['html'] and plain.called


def test_the_sitelist_names_the_required_backends() -> None:
    assert bypass_label(()) == ''
    assert bypass_label(('Impersonate',)) == 'Impersonate Required'
    assert bypass_label(('FlareSolverr', 'Impersonate')) == 'FlareSolverr and Impersonate Required'
    assert bypass_label(('FlareSolverr', 'Impersonate', 'Playwright')) == 'FlareSolverr, Impersonate and Playwright Required'
