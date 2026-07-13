from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites.jacquieetmichel import JacquieEtMichelClient
from app.registry import find_site

SITE = find_site('Jacquie Et Michel TV')
assert SITE is not None

DETAIL_HTML = """<html><body>
  <h1 class="content-detail__title">Ibiza 1 Crumb In The Mouth</h1>
  <div class="content-detail__description">A blurb.</div>
  <div class="content-detail__infos__row">
    <p class="content-detail__description--link">Studio</p>
    <p class="content-detail__description--link">2021-07-07</p>
  </div>
  <div class="content-detail__row"><ul>
    <li class="content-detail__tag">Sodomy,</li><li class="content-detail__tag">Orgy</li>
  </ul></div>
  <video poster="https://cdn.jm.com/poster.jpg"></video>
</body></html>"""


@respx.mock
async def test_search_cards() -> None:
    url = 'https://www.jacquieetmicheltv.net/en/content/list?search=ibiza'
    html = """<html><body>
      <a class="content-card content-card--video" href="/en/content/4554/ibiza-1-crumb-in-the-mouth">
        <h2 class="content-card__title">Ibiza 1</h2>
        <div class="content-card__date">Added on 2021-07-07</div>
      </a>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await JacquieEtMichelClient().search(results, SearchContext(title='ibiza', encoded='ibiza', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Ibiza 1'
    assert results[0].scene_url == 'https://www.jacquieetmicheltv.net/en/content/4554/ibiza-1-crumb-in-the-mouth'
    assert results[0].release_date == '2021-07-07'


@respx.mock
async def test_detail_genres_actors_from_fragment() -> None:
    url = 'https://www.jacquieetmicheltv.net/en/content/4554/ibiza-1-crumb-in-the-mouth'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    detail = await JacquieEtMichelClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Ibiza 1 Crumb In The Mouth'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'Jacquie Et Michel TV'
    assert detail.release_date == '2021-07-07'
    assert detail.genres == ['Anal', 'Orgy', 'French porn']
    assert [a.name for a in detail.actors] == ['Alexis Crystal', 'Cassie Del Isla', 'Dorian Del Isla']
    assert detail.art == ['https://cdn.jm.com/poster.jpg']
