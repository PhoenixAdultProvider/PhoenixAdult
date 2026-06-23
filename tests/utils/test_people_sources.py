from __future__ import annotations

import httpx
import pytest
import respx

from app.utils.people.sources import find_photo
from app.utils.people.sources.babepedia import babepedia_source
from app.utils.people.sources.boobpedia import boobpedia_source
from app.utils.people.sources.freeones import freeones_source
from app.utils.people.sources.indexxx import indexxx_source
from app.utils.people.sources.javBus import jav_bus_source
from app.utils.people.types import PersonLookupContext

CTX = PersonLookupContext(role='actor')

FREEONES_SEARCH = '<html><body><div class="grid-item"><a href="/jane-doe/feed">x</a></div></body></html>'
FREEONES_BIO = """<html><body>
  <h1>Jane Doe Bio</h1>
  <p>Aliases</p><div><p>JD, Janie</p></div>
  <p>Profession</p><div><p>Porn Stars</p></div>
  <div class="image-container"><a><img src="https://cdn.example.com/jane.jpg"></a></div>
</body></html>"""


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ACTOR_CACHE_ENABLE', 'false')


@respx.mock
async def test_freeones_match() -> None:
    respx.route(method='GET', url__regex=r'freeones\.com/babes').mock(return_value=httpx.Response(200, text=FREEONES_SEARCH))
    respx.route(method='GET', url__regex=r'freeones\.com/.+/bio').mock(return_value=httpx.Response(200, text=FREEONES_BIO))
    hit = await freeones_source.find('Jane Doe', CTX)
    assert hit is not None
    assert hit.url == 'https://cdn.example.com/jane.jpg'
    assert hit.gender == 'female'


@respx.mock
async def test_freeones_rejects_non_pornstar() -> None:
    bio = FREEONES_BIO.replace('Porn Stars', 'Singer')
    respx.route(method='GET', url__regex=r'freeones\.com/babes').mock(return_value=httpx.Response(200, text=FREEONES_SEARCH))
    respx.route(method='GET', url__regex=r'freeones\.com/.+/bio').mock(return_value=httpx.Response(200, text=bio))
    assert await freeones_source.find('Jane Doe', CTX) is None


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
async def test_javbus_search_match() -> None:
    html = '<div class="photo-frame"><a><img src="/pics/thumb/jane.jpg" title="Jane Doe"></a></div>'
    respx.route(method='GET', url__regex=r'javbus\.com/en/searchstar').mock(return_value=httpx.Response(200, text=html))
    hit = await jav_bus_source.find('Jane Doe', CTX)
    assert hit is not None and hit.url == 'https://www.javbus.com/pics/thumb/jane.jpg'


@respx.mock
async def test_find_photo_uses_first_hit() -> None:
    # Local Storage (cache off) returns nothing; Freeones is next in order.
    respx.route(method='GET', url__regex=r'freeones\.com/babes').mock(return_value=httpx.Response(200, text=FREEONES_SEARCH))
    respx.route(method='GET', url__regex=r'freeones\.com/.+/bio').mock(return_value=httpx.Response(200, text=FREEONES_BIO))
    hit = await find_photo('Jane Doe', CTX)
    assert hit.url == 'https://cdn.example.com/jane.jpg'
