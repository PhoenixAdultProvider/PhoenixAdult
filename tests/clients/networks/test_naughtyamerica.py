from __future__ import annotations

import httpx
import pytest
import respx

import app.clients.networks.naughtyamerica as na
from app.clients.base import SearchContext
from app.clients.networks.naughtyamerica import NaughtyAmericaClient
from app.registry import find_site

SITE = find_site('Naughty Office')
assert SITE is not None


@pytest.fixture(autouse=True)
def _no_pacing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(na, '_PACE_SECONDS', 0.0)


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


async def test_paced_serializes_and_spaces_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    import time as _t

    monkeypatch.setattr(na, '_PACE_SECONDS', 0.1)
    cl = NaughtyAmericaClient()

    async def _fake(url: str, ctx: object = None, label: object = None) -> dict[str, object]:
        return {'status': 200, 'html': '', 'sel': None}

    monkeypatch.setattr(cl, 'fetch_and_load', _fake)
    start = _t.monotonic()
    await cl._paced('u1')
    await cl._paced('u2')
    await cl._paced('u3')
    assert _t.monotonic() - start >= 0.2


@respx.mock
async def test_search_keyword_paginates() -> None:
    page1 = (
        '<html><body>'
        '<div class="scene-item scene-grid-item">'
        '  <a href="https://www.naughtyamerica.com/scene/scene-one-111" title="Scene One" data-scene-id="111"></a>'
        '  <p class="entry-date">March 4, 2021</p>'
        '</div>'
        '<li><a href="/search?term=x&page=2#2"><i class="fa double"></i></a></li>'
        '</body></html>'
    )
    page2 = (
        '<div class="scene-item scene-grid-item">'
        '  <a href="https://www.naughtyamerica.com/scene/scene-two-222" title="Scene Two" data-scene-id="222"></a>'
        '  <p class="entry-date">March 5, 2021</p>'
        '</div>'
    )
    respx.get('https://www.naughtyamerica.com/search?term=cool+scene&_gl=1').mock(return_value=httpx.Response(200, text=page1))
    respx.get('https://www.naughtyamerica.com/search?term=cool+scene&_gl=1&page=2').mock(return_value=httpx.Response(200, text=page2))
    results = await NaughtyAmericaClient().search(_ctx())
    titles = {r.title for r in results}
    assert titles == {'Scene One', 'Scene Two'}  # page 2 accumulated (legacy pagination)
    # curID/sceneURL are the full slug path, not the dead numeric /scene/0<id> form
    assert results[0].scene_url == 'https://www.naughtyamerica.com/scene/scene-one-111'


@respx.mock
async def test_detail() -> None:
    url = 'https://www.naughtyamerica.com/scene/cool-scene-555'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <div class="scene-info"><h1>Cool Scene</h1></div>
              <a class="site-title grey-text link">Naughty Office</a>
              <div class="date-tags"><span class="entry-date">March 4, 2021</span></div>
              <div class="synopsis grey-text"><h2>Synopsis</h2>A summary.</div>
              <div class="categories grey-text"><a>Office</a><a>Office</a></div>
              <div class="performer-list"><a>Jane Doe</a></div>
              <a class="play-trailer"><picture><source data-srcset="//images5.naughtycdn.com/cms/big.jpg" type="image/jpg"></picture></a>
            </body></html>""",
        )
    )
    respx.get('https://www.naughtyamerica.com/pornstar/jane-doe').mock(
        return_value=httpx.Response(200, text='<img class="performer-pic" data-src="//cdn/jane.jpg" />')
    )
    detail = await NaughtyAmericaClient().fetch_scene_detail('scene/cool-scene-555', SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Naughty America'
    assert detail.tagline == 'Naughty Office'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Office']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://cdn/jane.jpg'
    assert detail.raw_image_urls == ['https://images5.naughtycdn.com/cms/big.jpg']
