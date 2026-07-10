from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext
from app.clients.networks.kellymadison import KellyMadisonClient
from app.registry import find_site

SITE = find_site('PornFidelity')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '%20'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search_scene_id_score() -> None:
    url = 'https://www.pornfidelity.com/search?q=cool%20scene&type=episodes'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<a class="video-card" href="/episodes/777/cool-scene">
              <h3>Cool Scene</h3>
              <span class="video-title">Episode #1234</span>
              <time>03/04/21</time>
            </a>""",
        )
    )
    results = await KellyMadisonClient().search(_ctx(scene_id='1234'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://www.pornfidelity.com/episodes/777/cool-scene'
    assert results[0].score == 100
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_detail() -> None:
    url = 'https://www.pornfidelity.com/episodes/777/cool-scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1 class="title">TeenFidelity Cool Scene</h1>
              <div>Episode Summary<p>A summary.</p></div>
              <p>Published <strong>2021-03-04</strong></p>
              <p>Starring <a href="/models/jane">Jane Doe</a></p>
            </body></html>""",
        )
    )
    respx.get('https://www.pornfidelity.com/models/jane').mock(return_value=httpx.Response(200, text='<div class="one"><img src="/p/jane.jpg" /></div>'))
    detail = await KellyMadisonClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'TeenFidelity Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Kelly Madison Productions'
    assert detail.tagline == 'TeenFidelity'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Hardcore', 'Heterosexual']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://www.pornfidelity.com/p/jane.jpg'
    assert detail.raw_image_urls == [
        'https://tour-content-cdn.kellymadisonmedia.com/episode/poster_image/cool-scene/poster.jpg',
        'https://tour-content-cdn.kellymadisonmedia.com/episode/episode_thumb_image_1/cool-scene/1.jpg',
        'https://tour-content-cdn.kellymadisonmedia.com/episode/episode_thumb_image_1/cool-scene/01.jpg',
    ]
