from __future__ import annotations

import httpx
import pytest
import respx

import app.clients.networks.nubiles as nub_mod
from app.clients.base import SearchContext, SearchResult
from app.clients.networks.nubiles import NubilesClient
from app.registry import find_site

SITE = find_site('Nubile Films')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _no_pow(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake(_base: str) -> dict[str, str]:
        return {}

    monkeypatch.setattr(nub_mod, 'get_verified_cookies', _fake)


@respx.mock
async def test_search_scene_id() -> None:
    url = 'https://nubilefilms.com/video/watch/555'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text='<div class="content-pane-title"><h2>Cool Scene</h2><span class="date">March 4, 2021</span></div><video poster="//cdn/p.jpg"></video>',
        )
    )
    results: list[SearchResult] = []
    await NubilesClient().search(results, _ctx(scene_id='555'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].score == 100
    assert results[0].thumb_url == '//cdn/p.jpg'


@respx.mock
async def test_detail() -> None:
    url = 'https://nubilefilms.com/video/watch/555'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <div class="content-pane-title"><h2>Cool Scene - Part One</h2></div>
              <div class="col-12 content-pane-column"><div>A summary.Show More extra</div></div>
              <div class="content-pane"><span class="date">March 4, 2021</span></div>
              <div class="categories"><a>Teen</a><a>nubilefilms.com</a></div>
              <div class="content-pane-performer"><a href="/models/jane">Jane Doe</a></div>
              <div class="content-pane-related-links"><a href="/galleries/555/screenshots">Pics</a></div>
              <video poster="//cdn/p.jpg"></video>
            </body></html>""",
        )
    )
    respx.get('https://nubilefilms.com/models/jane').mock(
        return_value=httpx.Response(200, text='<div class="model-profile"><img src="//cdn/jane.jpg" /></div><p class="model-profile-subheading">Figure: 34</p>')
    )
    respx.get('https://nubilefilms.com/galleries/555/screenshots').mock(
        return_value=httpx.Response(200, text='<div class="img-wrapper"><picture><source srcset="//cdn/g1.jpg 800w, //cdn/g1-sm.jpg 400w" /></picture></div>')
    )
    detail = await NubilesClient().fetch_scene_detail('555|2021-03-04', SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene - Part One'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Nubiles'
    assert detail.tagline == 'Nubile Films'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Teen']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'http://cdn/jane.jpg'
    assert detail.actors[0].gender == 'female'
    assert detail.art == ['http://cdn/p.jpg', 'http://cdn/g1.jpg']


@respx.mock
async def test_summary_actor_injection() -> None:
    url = 'https://nubilefilms.com/video/watch/9'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <div class="content-pane-title"><h2>Cool</h2></div>
              <div class="col-12 content-pane-column"><div>Jane meets Johnny Castle and Van Wylde today.</div></div>
            </body></html>""",
        )
    )
    detail = await NubilesClient().fetch_scene_detail('9', SITE)
    assert detail is not None
    names = [a.name for a in detail.actors or []]
    assert names == ['Van Wylde', 'Johnny Castle']
    assert all(a.gender == 'male' for a in detail.actors or [])
