from __future__ import annotations

import httpx
import pytest
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites import putalocura as pl_module
from app.clients.sites.putalocura import PutalocuraClient
from app.registry import find_site

SITE = find_site('Putalocura')
assert SITE is not None

DETAIL_HTML = """<html><head><title>Casting Alika - Putalocura | x</title></head><body>
  <div class="released-views"><span>05/05/2021</span></div>
  <div class="description clearfix">Descripcion: A blurb.
  second line</div>
  <div class="categories"><a>Casting</a><a>Amateur</a></div>
  <span class="site-name">Alika</span>
  <div class="top-area-content"><script>var x = {posterImage: "https://cdn.pl.com/poster.jpg"};</script></div>
</body></html>"""

MODEL_INDEX_A = """<html><body>
  <a><div class="c-boxlist__box--image"><img src="/img/alyka.jpg"></div>Alyka</a>
</body></html>"""


@respx.mock
async def test_search_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    scene_url = 'https://www.putalocura.com/casting-alika'

    async def _web(*_a: object, **_k: object) -> list[str]:
        return [scene_url, 'https://www.putalocura.com/tags/casting']

    monkeypatch.setattr(pl_module, 'web_search', _web)
    respx.get(scene_url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    results: list[SearchResult] = []
    await PutalocuraClient().search(results, SearchContext(title='alika', encoded='alika', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Casting Alika'
    assert results[0].release_date == '2021-05-05'


@respx.mock
async def test_detail_actors_remap_photo() -> None:
    url = 'https://www.putalocura.com/casting-alika'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    respx.get('https://www.putalocura.com/actrices/a').mock(return_value=httpx.Response(200, text=MODEL_INDEX_A))
    respx.get('https://www.putalocura.com/actrices/c').mock(return_value=httpx.Response(200, text='<html><body></body></html>'))
    detail = await PutalocuraClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Casting Alika'
    assert detail.summary == 'A blurb. second line'
    assert detail.studio == 'Putalocura'
    assert detail.release_date == '2021-05-05'
    assert detail.genres == ['Casting', 'Amateur']
    assert [a.name for a in detail.actors] == ['Alyka']
    assert detail.actors[0].photo_url == 'https://www.putalocura.com/img/alyka.jpg'
    assert detail.raw_image_urls == ['https://cdn.pl.com/poster.jpg']
