from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites.inthecrack import InTheCrackClient
from app.registry import find_site

SITE = find_site('In The Crack')
assert SITE is not None

INDEX_HTML = """<html><body>
  <ul class="collectionGridLayout">
    <li><span>Alice Wonder</span><a href="/model/alice-wonder">x</a></li>
  </ul>
</body></html>"""

MODEL_HTML = """<html><body>
  <ul class="Models"><li>
    <a href="/Collections/1234">x</a>
    <figure><p>Collection: 1234</p><p>Release Date: 2021-02-02</p></figure>
  </li></ul>
</body></html>"""

DETAIL_HTML = """<html><head><title>InTheCrack #1234 Alice Wonder & Bea Star</title></head><body>
  <h2><span>Collection 1234</span></h2>
  <p id="CollectionDescription">A blurb.</p>
  <style>.bg { background-image: url('/images/1234.jpg'); }</style>
</body></html>"""


@respx.mock
async def test_search_three_hop() -> None:
    respx.get('https://inthecrack.com/Collections/Name/a').mock(return_value=httpx.Response(200, text=INDEX_HTML))
    respx.get('https://inthecrack.com/model/alice-wonder').mock(return_value=httpx.Response(200, text=MODEL_HTML))
    results: list[SearchResult] = []
    await InTheCrackClient().search(results, SearchContext(title='alice', encoded='alice', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == '1234'
    assert results[0].scene_url == 'https://inthecrack.com/Collections/1234'
    assert results[0].release_date == '2021-02-02'


@respx.mock
async def test_detail_title_actors_image() -> None:
    url = 'https://inthecrack.com/Collections/1234'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    detail = await InTheCrackClient().fetch_scene_detail(f'{url}|2021-02-02', SITE)
    assert detail is not None
    assert detail.title == 'Collection 1234'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'InTheCrack'
    assert detail.collections == ['In The Crack']
    assert detail.release_date == '2021-02-02'
    assert detail.genres == ['Solo']
    assert [a.name for a in detail.actors] == ['Alice Wonder', 'Bea Star']
    assert detail.art == ['https://inthecrack.com/images/1234.jpg']
