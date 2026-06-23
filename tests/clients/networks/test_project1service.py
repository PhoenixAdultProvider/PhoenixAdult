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
