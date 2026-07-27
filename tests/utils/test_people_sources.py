from __future__ import annotations

import httpx
import pytest
import respx

import phoenixadult.utils.people.sources as people_sources
from phoenixadult.utils.people.sources import find_photo
from phoenixadult.utils.people.sources.babepedia import babepedia_source
from phoenixadult.utils.people.sources.boobpedia import boobpedia_source
from phoenixadult.utils.people.sources.indexxx import indexxx_source
from phoenixadult.utils.people.types import PersonLookupContext, PhotoHit

CTX = PersonLookupContext(type='actor')


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('PEOPLE_CACHE_ENABLE', 'false')


@respx.mock
async def test_indexxx_match() -> None:
    search = '<div class="modelPanel"><a class="modelLink3" href="https://www.indexxx.com/m/jane/">x</a></div>'
    page = '<img class="model-img" src="https://cdn.example.com/jane2.jpg">'
    respx.route(method='GET', url__regex=r'indexxx\.com/search').mock(return_value=httpx.Response(200, text=search))
    respx.route(method='GET', url__regex=r'indexxx\.com/m/jane').mock(return_value=httpx.Response(200, text=page))
    hit = await indexxx_source.find('Jane Doe', CTX)
    assert hit is not None and hit.url == 'https://cdn.example.com/jane2.jpg'


@respx.mock
async def test_boobpedia_match() -> None:
    html = '<table class="infobox"><a class="image"><img src="/img/jane.jpg"></a></table>'
    respx.route(method='GET', url__regex=r'boobpedia\.com/boobs/Jane_Doe').mock(return_value=httpx.Response(200, text=html))
    hit = await boobpedia_source.find('Jane Doe', CTX)
    assert hit is not None and hit.url == 'http://www.boobpedia.com/img/jane.jpg'


@respx.mock
async def test_babepedia_head_ok() -> None:
    respx.route(method='HEAD', url__regex=r'babepedia\.com/pics').mock(return_value=httpx.Response(200))
    hit = await babepedia_source.find('Jane Doe', CTX)
    assert hit is not None and hit.url.endswith('Jane%20Doe.jpg')


@respx.mock
async def test_babepedia_head_404() -> None:
    respx.route(method='HEAD', url__regex=r'babepedia\.com/pics').mock(return_value=httpx.Response(404))
    assert await babepedia_source.find('Jane Doe', CTX) is None


@respx.mock
async def test_find_photo_uses_first_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Nothing:
        name = 'Nothing'

        async def find(self, _name: str, _ctx: PersonLookupContext) -> PhotoHit | None:
            return None

    search = '<div class="modelPanel"><a class="modelLink3" href="https://www.indexxx.com/m/jane/">x</a></div>'
    page = '<img class="model-img" src="https://cdn.example.com/jane2.jpg">'
    respx.route(method='GET', url__regex=r'indexxx\.com/search').mock(return_value=httpx.Response(200, text=search))
    respx.route(method='GET', url__regex=r'indexxx\.com/m/jane').mock(return_value=httpx.Response(200, text=page))
    monkeypatch.setattr(people_sources, '_configured_order', lambda: [_Nothing(), indexxx_source])
    hit = await find_photo('Jane Doe', CTX)
    assert hit.url == 'https://cdn.example.com/jane2.jpg'


async def test_find_photo_keeps_gender_without_url(monkeypatch: pytest.MonkeyPatch) -> None:
    class _GenderOnly:
        name = 'GenderOnly'

        async def find(self, _name: str, _ctx: PersonLookupContext) -> PhotoHit:
            return PhotoHit(url='', gender='male')

    monkeypatch.setattr(people_sources, '_configured_order', lambda: [_GenderOnly()])
    hit = await find_photo('Ken Shiro', CTX)
    assert hit.url == '' and hit.gender == 'male'
