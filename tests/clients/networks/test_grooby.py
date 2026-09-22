from __future__ import annotations

import httpx
import pytest
import respx

import phoenixadult.clients.networks.grooby as grooby_mod
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site

SITE = find_site('Grooby Girls')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '%20'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search(monkeypatch: pytest.MonkeyPatch) -> None:

    async def fake_filtered(*_a: object, **_k: object) -> list[str]:
        return ['https://www.groobygirls.com/tour/trailers/cool.html?x=1']

    monkeypatch.setattr(grooby_mod, 'web_search_urls', fake_filtered)
    respx.get('https://www.groobygirls.com/tour/trailers/cool.html').mock(
        return_value=httpx.Response(200, text='<div class="trailer_videoinfo"><h3>Cool Scene</h3></div><div class="setdesc">Added - March 4, 2021</div>')
    )
    results: list[SearchResult] = []
    await grooby_mod.GroobyClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://www.groobygirls.com/tour/trailers/cool.html'
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_detail() -> None:
    url = 'https://www.groobygirls.com/tour/trailers/cool.html'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <div class="trailer_videoinfo"><h3>Cool Scene</h3>
                <p>Featuring: <a href="/models/jane">Jane Doe</a></p>
                <p>The summary.</p>
              </div>
              <div class="setdesc">Added - March 4, 2021</div>
              <div class="trailerposter"><img src0_4x="/img/poster.jpg" /></div>
            </body></html>""",
        )
    )
    respx.get('https://www.groobygirls.com/models/jane').mock(
        return_value=httpx.Response(200, text='<div class="model_photo"><img id="x" src0_1x="/p/jane.jpg" /></div>')
    )
    detail = await grooby_mod.GroobyClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'The summary.'
    assert detail.studio == 'Grooby'
    assert detail.tagline == 'Grooby Girls'
    assert detail.release_date == '2021-03-04'
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://www.groobygirls.com/p/jane.jpg'
    assert detail.art == ['https://www.groobygirls.com/img/poster.jpg']
