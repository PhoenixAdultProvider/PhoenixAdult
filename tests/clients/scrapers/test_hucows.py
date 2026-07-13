from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites.hucows import HucowsClient
from app.registry import find_site

SITE = find_site('HuCows')
assert SITE is not None


@respx.mock
async def test_search_keyword_articles() -> None:
    url = 'https://www.hucows.com/?s=milk+time'
    html = """<html><body>
      <article>
        <a href="/category/x">cat</a>
        <a href="/scene/milk-time">scene</a>
        <h2>Milk Time</h2>
        <div itemprop="datePublished">12 Jul 2021</div>
      </article>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await HucowsClient().search(results, SearchContext(title='milk time', encoded='milk+time', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Milk Time'
    assert results[0].scene_url == 'https://www.hucows.com/scene/milk-time'
    assert results[0].release_date == '2021-07-12'


@respx.mock
async def test_detail_fields_genres_actors_images() -> None:
    url = 'https://www.hucows.com/scene/milk-time'
    html = """<html><head><title>Milk Time - HuCows.com</title></head><body>
      <article><div class="entry-content"><p>A blurb.</p></div></article>
      <div itemprop="datePublished">Release Date: 12 Jul 2021</div>
      <span><a rel="category tag">Lactation</a></span>
      <a rel="tag">Alice</a>
      <article><div><a class="lightboxhover"><img src="https://cdn.hc.com/p1.jpg"></a></div></article>
      <center><a><img class="lightboxhover" src="/p2.jpg"></a></center>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    detail = await HucowsClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Milk Time'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'HuCows'
    assert detail.collections == ['HuCows']
    assert detail.release_date == '2021-07-12'
    assert detail.genres == ['BDSM', 'Breast Torture', 'Breasts', 'Fetish', 'HuCows', 'Nipple Torture', 'Nipples', 'Lactation']
    assert [a.name for a in detail.actors] == ['Alice']
    assert detail.raw_image_urls == ['https://cdn.hc.com/p1.jpg', 'https://www.hucows.com/p2.jpg']
