from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.networks.julesjordan import JulesJordanClient
from phoenixadult.registry import find_site

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
    assert detail.art == ['https://www.julesjordan.com/img/poster.jpg']


@respx.mock
async def test_search_parses_the_new_card_layout_with_dates() -> None:
    respx.get('https://www.julesjordan.com/trial/scenes/cool-scene_vids.html').mock(return_value=httpx.Response(404, text=''))
    respx.get('https://www.julesjordan.com/trial/search.php?query=cool+scene').mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <div class="search-scene-card">
                <a class="jj-card-thumb" href="/trial/scenes/cool-scene_vids.html"></a>
                <h2 class="jj-card-title">Cool Scene</h2>
                <div class="jj-card-date">Released: March 4, 2021</div>
              </div>
            </body></html>""",
        )
    )
    results: list[SearchResult] = []
    await JulesJordanClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].display_date == '2021-03-04'
    assert '2021-03-04' in JulesJordanClient().decode(results[0].cur_id)


@respx.mock
async def test_detail_parses_the_new_layout_with_the_site_as_studio() -> None:
    site = find_site('GirlGirl')
    assert site is not None
    url = 'https://www.girlgirl.com/trial/scenes/cool-scene_vids.html'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1 class="scene-title">Cool Scene</h1>
              <div class="scene-desc">A summary.</div>
              <div class="meta-item"><div>Movie</div><div>Cool Movie</div></div>
              <div class="meta-item"><div>Released</div><div>March 4, 2021</div></div>
              <div class="scene-cats"><a>Anal</a><a>Gonzo</a></div>
              <div class="scene-info"><span class="update_models"><a href="/trial/models/jane.html">Jane Doe</a></span></div>
              <div class="tp-photos-strip"><img src="/img/g1.jpg"><img src="/img/g2.jpg"></div>
              <video id="video-player" poster="/img/poster.jpg"></video>
            </body></html>""",
        )
    )
    respx.get('https://www.girlgirl.com/trial/models/jane.html').mock(return_value=httpx.Response(200, text='<img src="/contentthumbs/jane-1x.jpg" />'))
    detail = await JulesJordanClient().fetch_scene_detail(url, site)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'GirlGirl'
    assert detail.tagline == 'Cool Movie'
    assert detail.collections == ['GirlGirl']
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['anal', 'gonzo']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://www.girlgirl.com/contentthumbs/jane-1x.jpg'
    assert detail.art == ['https://www.girlgirl.com/img/g1.jpg', 'https://www.girlgirl.com/img/g2.jpg', 'https://www.girlgirl.com/img/poster.jpg']
