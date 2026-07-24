"""Base Client fetch_logo: runs after update() with studio/tagline final, and a
failing hook never breaks the scene."""

from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.base import Client, LoadedScene, SceneDetail
from phoenixadult.registry import find_site

SITE = find_site('Brazzers')
assert SITE is not None

_PAGE = httpx.Response(200, text='<html><h1>x</h1></html>')


class _LogoClient(Client):
    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = 'Baby Got Boobs'

    async def fetch_logo(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.logo = f'logo-for:{metadata.tagline or metadata.studio}'


class _BoomClient(Client):
    async def fetch_logo(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        raise ValueError('boom')


@respx.mock
async def test_fetch_logo_sees_final_tagline_and_studio_fallback() -> None:
    respx.get('https://x.test/scene').mock(return_value=_PAGE)
    detail = await _LogoClient().fetch_scene_detail('https://x.test/scene', SITE)
    assert detail is not None
    assert detail.logo == 'logo-for:Baby Got Boobs'
    assert detail.studio == SITE.name


@respx.mock
async def test_fetch_logo_failure_is_isolated() -> None:
    respx.get('https://x.test/scene').mock(return_value=_PAGE)
    detail = await _BoomClient().fetch_scene_detail('https://x.test/scene', SITE)
    assert detail is not None
    assert detail.logo is None
