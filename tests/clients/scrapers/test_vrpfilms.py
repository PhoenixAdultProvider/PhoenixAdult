from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites.vrpfilms import VRPFilmsClient
from app.registry import find_site

SITE = find_site('VRPFilms')
assert SITE is not None


@respx.mock
async def test_search_direct_slug() -> None:
    url = 'https://vrpfilms.com/m/wild-scene-title'
    respx.get(url).mock(
        return_value=httpx.Response(200, text='<html><body><section class="login-banner parallax"><h1>Wild Scene Title</h1></section></body></html>')
    )
    results: list[SearchResult] = []
    await VRPFilmsClient().search(results, SearchContext(title='Wild Scene Title', encoded='x', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].scene_url == url
    assert results[0].title == 'Wild Scene Title'


@respx.mock
async def test_search_empty_on_404() -> None:
    respx.get('https://vrpfilms.com/m/no-such-scene').mock(return_value=httpx.Response(404, text=''))
    results: list[SearchResult] = []
    await VRPFilmsClient().search(results, SearchContext(title='No Such Scene', encoded='x', search_site=SITE.name, site_info=SITE))
    assert results == []


@respx.mock
async def test_detail() -> None:
    url = 'https://vrpfilms.com/m/wild-scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <section class="login-banner parallax" style="background-image: url('https://cdn.vrp.com/bg.jpg')">
                <h1>Wild Scene</h1>
              </section>
              <div class="col-md-8 text-justify">A wild scene blurb.</div>
              <div class="single__download tags">Anal, Hardcore, Threesome</div>
              <a class="starring_contain" href="/star/jane">
                <div class="starring_image" style="background-image: url('https://cdn.vrp.com/jane.jpg')"></div>
                <div class="col-xs-12 video-star-title"><h3>Jane Doe</h3></div>
              </a>
              <a class="starring_contain" href="/star/mary">
                <div class="starring_image" style="background-image: url('https://cdn.vrp.com/mary.jpg')"></div>
                <div class="col-xs-12 video-star-title"><h3>Mary Roe</h3></div>
              </a>
              <div class="col-md-12 gallery-body">
                <div><div><div><a href="https://cdn.vrp.com/g1.jpg">g1</a></div></div></div>
                <div><div><div><a href="https://cdn.vrp.com/g2.jpg">g2</a></div></div></div>
              </div>
            </body></html>""",
        )
    )
    detail = await VRPFilmsClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Wild Scene'
    assert detail.summary == 'A wild scene blurb.'
    assert detail.studio == 'VRPFilms'
    assert detail.tagline is None
    assert detail.collections == ['VRPFilms']
    assert detail.genres == ['Anal', 'Hardcore', 'Threesome']
    assert [(a.name, a.photo_url) for a in detail.actors] == [
        ('Jane Doe', 'https://cdn.vrp.com/jane.jpg'),
        ('Mary Roe', 'https://cdn.vrp.com/mary.jpg'),
    ]
    assert detail.raw_image_urls == ['https://cdn.vrp.com/bg.jpg', 'https://cdn.vrp.com/g1.jpg', 'https://cdn.vrp.com/g2.jpg']
