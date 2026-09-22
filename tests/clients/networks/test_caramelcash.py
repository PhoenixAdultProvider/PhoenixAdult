from __future__ import annotations

import httpx
import pytest
import respx

import phoenixadult.clients.networks.caramelcash as cc_mod
from phoenixadult.clients.networks.caramelcash import CaramelCashClient, __testing__
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site


async def _no_web_search(*_a: object, **_k: object) -> list[str]:
    return []


SITE = find_site('Alex Legend')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '%20'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search_direct_scene_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cc_mod, 'web_search_urls', _no_web_search)
    url = 'https://alexlegend.com/video/555'
    respx.get(url).mock(return_value=httpx.Response(200, text='<h1>Cool Scene</h1><div class="content-date">04.03.2021</div>'))
    results: list[SearchResult] = []
    await CaramelCashClient().search(results, _ctx(scene_id='555'))
    assert len(results) == 1
    assert results[0].scene_url == url
    assert results[0].title == 'Cool Scene'
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_detail() -> None:
    url = 'https://alexlegend.com/video/555'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <div class="content-title">Cool Scene</div>
              <div class="content-desc">skip me</div>
              <div class="content-desc">A summary.</div>
              <div class="content-date">Date: 12th May 2024</div>
              <div class="content-tags"><a>Anal</a><a>Anal</a><a>Gonzo</a></div>
              <section class="content-sec backdrop"><div class="main__models"><a>Jane Doe</a></div></section>
              <section class="content-gallery-sec"><a data-lightbox="gallery" href="https://cdn/g1.jpg"></a></section>
            </body></html>""",
        )
    )
    detail = await CaramelCashClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Caramel Cash'
    assert detail.tagline == 'Alex Legend'
    assert detail.collections == ['Alex Legend']
    assert detail.release_date == '2024-05-12'
    assert detail.genres == ['Anal', 'Gonzo']
    assert [a.name for a in detail.actors] == ['Jane Doe']
    assert detail.art == ['https://cdn/g1.jpg']


def test_parse_caramel_date() -> None:
    p = __testing__['parse_caramel_date']
    assert p('04.03.2021') == '2021-03-04'
    assert p('Date: 12th May 2024') == '2024-05-12'
    assert p('') is None
