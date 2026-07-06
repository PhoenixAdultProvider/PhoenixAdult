from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext
from app.clients.networks.project1service import Project1ServiceClient, _service_url
from app.registry import find_site

SITE = find_site('Brazzers')
assert SITE is not None
_API = 'https://site-api.project1service.com'


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


def _token_head() -> None:
    respx.head('http://www.brazzers.com').mock(return_value=httpx.Response(200, headers=[('set-cookie', 'instance_token=tok123; Path=/')]))


def test_service_url() -> None:
    assert _service_url('akamai=hash/path/p.jpg', 'https://img.example.com/') == 'https://img.example.com/path/p.jpg'
    assert _service_url(None, 'https://img.example.com/') is None


_RELEASE = {
    'id': 777,
    'title': 'Cool Scene',
    'description': 'A summary.',
    'brand': 'Brazzers',
    'dateReleased': '2021-03-04 00:00:00',
    'collections': [{'name': 'Pornstars Like It Big'}],
    'tags': [{'name': 'Anal'}],
    'actors': [{'id': 5, 'name': 'Jane Doe'}],
    'images': {'poster': {'0': {'xx': {'url': 'akamai=hash/path/p.jpg'}}}},
}


@respx.mock
async def test_search() -> None:
    _token_head()
    respx.get(url__startswith=f'{_API}/v2/releases').mock(return_value=httpx.Response(200, json={'result': [_RELEASE]}))
    results = await Project1ServiceClient().search(_ctx())
    titles = {r.title for r in results}
    assert 'Cool Scene' in titles
    assert '[Trailer] Cool Scene' in titles  # trailer type prefixed
    cool = next(r for r in results if r.title == 'Cool Scene')
    assert cool.thumb_url == 'https://image-service-ht.project1content.com/path/p.jpg'
    assert cool.release_date == '2021-03-04'
    assert cool.display_date == '2021-03-04'


@respx.mock
async def test_search_date_falls_back_to_filename_date() -> None:
    _token_head()
    dateless = {**_RELEASE, 'dateReleased': None}
    respx.get(url__startswith=f'{_API}/v2/releases').mock(return_value=httpx.Response(200, json={'result': [dateless]}))
    results = await Project1ServiceClient().search(_ctx(search_date='2021-03-04'))
    cool = next(r for r in results if r.title == 'Cool Scene')
    assert cool.release_date == '2021-03-04'  # API omitted dateReleased -> filename date used for release_date
    assert cool.display_date is None  # display_date is the scene's own date only, never the filename date


@respx.mock
async def test_detail() -> None:
    _token_head()
    respx.get(url__startswith=f'{_API}/v2/releases').mock(return_value=httpx.Response(200, json={'result': [_RELEASE]}))
    actor = {'id': 5, 'name': 'Jane Doe', 'gender': 'female', 'images': {'profile': {'0': {'xs': {'url': 'x=h/a/jane.jpg'}}}}}
    respx.get(url__startswith=f'{_API}/v1/actors').mock(return_value=httpx.Response(200, json={'result': [actor]}))
    detail = await Project1ServiceClient().fetch_scene_detail('777|scene|2021-03-04', SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Brazzers'
    assert detail.tagline == 'Pornstars Like It Big'  # sub-site != studio
    assert detail.collections == ['Pornstars Like It Big']
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Anal']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].gender == 'female'
    assert detail.actors[0].photo_url == 'https://image-service-ht.project1content.com/a/jane.jpg'
    assert detail.raw_image_urls == ['https://image-service-ht.project1content.com/path/p.jpg']


@respx.mock
async def test_search_forces_brazzers_live_subsite() -> None:
    _token_head()
    live = find_site('Brazzers Live')
    assert live is not None
    respx.get(url__startswith=f'{_API}/v2/releases').mock(return_value=httpx.Response(200, json={'result': [_RELEASE]}))
    ctx = SearchContext(title='cool scene', encoded='cool+scene', search_site='Brazzers Live', site_info=SITE)
    results = await Project1ServiceClient().search(ctx)
    cool = next(r for r in results if r.title == 'Cool Scene')
    assert 'sub=Brazzers Live' in Project1ServiceClient().decode(cool.cur_id)


@respx.mock
async def test_detail_forced_subsite_overrides_tagline_and_collection() -> None:
    _token_head()
    respx.get(url__startswith=f'{_API}/v2/releases').mock(return_value=httpx.Response(200, json={'result': [_RELEASE]}))
    respx.get(url__startswith=f'{_API}/v1/actors').mock(return_value=httpx.Response(200, json={'result': []}))
    detail = await Project1ServiceClient().fetch_scene_detail('777|scene|2021-03-04|sub=Brazzers Live', SITE)
    assert detail is not None
    assert detail.studio == 'Brazzers'  # network studio unchanged
    assert detail.tagline == 'Brazzers Live'  # forced from the searched alias
    assert detail.collections == ['Brazzers Live']
