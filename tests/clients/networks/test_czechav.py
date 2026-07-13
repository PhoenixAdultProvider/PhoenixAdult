from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.networks.czechav import CzechAVClient
from app.registry import find_site

SITE = find_site('Czech Massage')
CASTING = find_site('Czech Casting')
assert SITE is not None and CASTING is not None


def _ctx(site: object, title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '%20'), search_site=site.name, site_info=site, **kw)  # type: ignore[union-attr,arg-type]


@respx.mock
async def test_search_scene_id_boost() -> None:
    url = 'https://czechmassage.com/tour/search/?q=cool%20scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<div class="search-item">
              <a href="/video/cool-scene-555/"><h2>Cool Scene</h2></a>
              <img src="https://cdn/t.jpg" />
            </div>""",
        )
    )
    results: list[SearchResult] = []
    await CzechAVClient().search(results, _ctx(SITE, scene_id='555'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://czechmassage.com/video/cool-scene-555/'
    assert results[0].score == 100
    assert results[0].thumb_url == 'https://cdn/t.jpg'


@respx.mock
async def test_detail_episode() -> None:
    url = 'https://czechmassage.com/video/cool-scene-555/'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1>Czech Massage: Cool Scene</h1>
              <div class="read-more"><p>intro</p><p>The real summary.</p></div>
              <ul class="tags"><li>Massage</li><li>Massage</li><li>Oil</li></ul>
              <meta property="og:image" content="https://cdn/og.jpg" />
              <img class="thumb" src="/img/t1.jpg" />
              <div class="gallery"><a href="https://cdn/gal1.jpg"></a></div>
            </body></html>""",
        )
    )
    detail = await CzechAVClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'The real summary.'
    assert detail.studio == 'Czech Authentic Videos'
    assert detail.tagline == 'Czech Massage'
    assert detail.genres == ['Massage', 'Oil']
    assert detail.actors == []
    assert detail.art == ['https://cdn/og.jpg', 'https://czechmassage.com/img/t1.jpg']


@respx.mock
async def test_detail_casting_actor() -> None:
    url = 'https://czechcasting.com/video/girl-1/'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1>Girl Name</h1>
              <span class="name">Girl Name</span><span class="age">24</span>
              <div class="gallery"><a href="https://cdn/g1.jpg"></a></div>
            </body></html>""",
        )
    )
    detail = await CzechAVClient().fetch_scene_detail(url, CASTING)
    assert detail is not None
    assert detail.actors[0].name == 'Girl Name 24'
    assert detail.actors[0].photo_url == 'https://cdn/g1.jpg'
