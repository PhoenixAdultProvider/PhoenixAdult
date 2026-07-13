from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.networks.julesjordan import JulesJordanClient
from app.registry import find_site

SITE = find_site('Jules Jordan')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search_direct() -> None:
    direct = 'https://www.julesjordan.com/trial/scenes/cool-scene_vids.html'
    respx.get(direct).mock(return_value=httpx.Response(200, text='<html></html>'))
    respx.get('https://www.julesjordan.com/trial/search.php?query=cool+scene').mock(return_value=httpx.Response(200, text='<html></html>'))
    results: list[SearchResult] = []
    await JulesJordanClient().search(results, _ctx())
    assert results[0].scene_url == direct
    assert results[0].score == 100


@respx.mock
async def test_detail() -> None:
    url = 'https://www.julesjordan.com/trial/scenes/cool-scene_vids.html'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <div class="movie_title">Cool Scene</div>
              <div class="player-scene-description">
                <div><span>Description:</span> A summary.</div>
                <div><span>Movie:</span> Cool Movie</div>
                <div><span>Date:</span> March 4, 2021</div>
                <div><span>Starring:</span> <a href="/trial/models/jane.html">Jane Doe</a></div>
              </div>
              <span>Categories: <a>Anal</a><a>Gonzo</a></span>
              <video id="video-player" poster="/img/poster.jpg"></video>
            </body></html>""",
        )
    )
    respx.get('https://www.julesjordan.com/trial/models/jane.html').mock(
        return_value=httpx.Response(200, text='<img class="model_bio_thumb stdimage thumbs target" src0_3x="/p/jane.jpg" />')
    )
    respx.get('https://www.julesjordan.com/trial/search.php?query=Cool%20Scene').mock(return_value=httpx.Response(200, text='<html></html>'))
    detail = await JulesJordanClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Jules Jordan'
    assert detail.tagline == 'Cool Movie'
    assert detail.collections == ['Jules Jordan']
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['anal', 'gonzo']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://www.julesjordan.com/p/jane.jpg'
    assert detail.raw_image_urls == ['https://www.julesjordan.com/img/poster.jpg']
