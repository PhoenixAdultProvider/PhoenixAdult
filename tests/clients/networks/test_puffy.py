from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.networks.puffy import PuffyClient
from phoenixadult.registry import find_site

SITE = find_site('Wet and Pissy')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search() -> None:
    url = 'https://www.puffynetwork.com/videos?search=cool+scene'
    respx.get(url).mock(
        return_value=httpx.Response(200, text='<div style="position:relative; background:black;"><a href="/v/cool-video-77" title="Cool Scene"></a></div>')
    )
    results: list[SearchResult] = []
    await PuffyClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://www.puffynetwork.com/v/cool-video-77'


@respx.mock
async def test_detail() -> None:
    url = 'https://www.puffynetwork.com/v/cool-video-77'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body><div>
              <section><div></div><div><h2><span>Cool Scene</span></h2></div></section>
              <section><dl><dt>x</dt><dt>Released on: March 4, 2021</dt><dd><a href="/model/jane">Jane Doe</a></dd></dl></section>
              <section><div></div><div>A summary.<p><a>Anal</a></p></div></section>
            </div></body></html>""",
        )
    )
    respx.get('https://www.puffynetwork.com/model/jane').mock(
        return_value=httpx.Response(200, text='<div><section><div><div><img src="https://cdn/jane.jpg" /></div></div></section></div>')
    )
    detail = await PuffyClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Puffy Network'
    assert detail.tagline == 'Wet and Pissy'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Anal']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://cdn/jane.jpg'
    assert 'https://media.wetandpissy.com/videos/video-77cover/hd.jpg' in detail.art
