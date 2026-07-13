from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.networks.blurredmedia import BlurredMediaClient
from app.registry import find_site

SITE = find_site('Gay Hoopla')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '%20'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search() -> None:
    url = 'https://gayhoopla.com/videos/search?s=cool+scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<article class="video grid-element">
              <a href="/videos/77/cool-scene"></a>
              <h3 class="video__title">Cool Scene</h3>
              <p class="video__stats">Mar 4, 2021 | 12:00</p>
            </article>""",
        )
    )
    results: list[SearchResult] = []
    await BlurredMediaClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://gayhoopla.com/videos/77/cool-scene'
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_detail() -> None:
    url = 'https://gayhoopla.com/videos/77/cool-scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1 class="title">Cool Scene</h1>
              <section name="descriptionIntro"><p>A summary.</p></section>
              <time class="video__date" datetime="2021-03-04"></time>
              <a class="video__tag">Anal</a><a class="video__tag">Anal</a><a class="video__tag">Twink</a>
              <section name="modelsBio"><article><figure>
                <p><a>Jane Doe</a></p><img src="/img/jane.jpg" />
              </figure></article></section>
              <div class="loading-video"><img src="/img/main.jpg" /></div>
              <ul class="thumbnails__gallery"><li><a href="https://cdn/g1.jpg"></a></li></ul>
            </body></html>""",
        )
    )
    detail = await BlurredMediaClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Gay Hoopla'
    assert detail.collections == ['Gay Hoopla']
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Anal', 'Twink']
    assert [a.name for a in detail.actors] == ['Jane Doe']
    assert detail.actors[0].photo_url == 'https://gayhoopla.com/img/jane.jpg'
    assert detail.raw_image_urls == ['https://gayhoopla.com/img/main.jpg', 'https://cdn/g1.jpg']
