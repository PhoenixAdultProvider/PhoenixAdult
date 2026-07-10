from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext
from app.clients.networks.porncz import PornCZClient
from app.registry import find_site

SITE = find_site('Czech Sex Casting')
DOLLS = find_site('Czech Real Dolls')
assert SITE is not None and DOLLS is not None


def _ctx(site, title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=site.name, site_info=site, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search() -> None:
    url = 'https://www.czechsexcasting.com/en/search?q=cool+scene'
    html = (
        '<div class="card--item"><div class="card-body"><a href="/en/video/7">Cool Scene</a></div><div class="card__img"><img data-src="/t.jpg" /></div></div>'
    )
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results = await PornCZClient().search(_ctx(SITE))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://www.czechsexcasting.com/en/video/7'
    assert results[0].thumb_url == 'https://www.czechsexcasting.com/t.jpg'


@respx.mock
async def test_detail_dolls_gender_tag() -> None:
    url = 'https://www.czechrealdolls.com/en/video/9'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><head><meta property="video:release_date" content="04.03.2021" /></head><body>
              <h1>Cool Scene</h1>
              <div class="dmb-1"><p>A summary.</p></div>
              <div class="video-info"><a href="/en/videos?category=1">#Anal</a></div>
              <div class="mini-avatars"><a href="/en/model/jane">Jane Doe</a></div>
              <a class="gallery-popup" href="/g/1.jpg"></a>
            </body></html>""",
        )
    )
    actor = '<img class="actor-img" data-src="/p/jane.jpg" /><div class="model-info__item"><span><i></i>Female</span></div>'
    respx.get('https://www.czechrealdolls.com/en/model/jane').mock(return_value=httpx.Response(200, text=actor))
    detail = await PornCZClient().fetch_scene_detail(url, DOLLS)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'PornCZ'
    assert detail.tagline == 'Czech Real Dolls'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Anal']
    assert detail.actors[0].name == 'Jane Doe (Sex Doll)'
    assert detail.actors[0].gender == 'female'
    assert detail.actors[0].photo_url == 'https://www.czechrealdolls.com/p/jane.jpg'
    assert detail.raw_image_urls == ['https://www.czechrealdolls.com/g/1.jpg']
