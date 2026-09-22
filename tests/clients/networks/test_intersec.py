from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.networks.intersec import IntersecClient
from phoenixadult.models.scrape import SearchResult
from phoenixadult.registry import find_site
from tests.support import search_context

SITE = find_site('Insex')
assert SITE is not None


@respx.mock
async def test_search_packs_cover() -> None:
    url = 'https://www.insexondemand.com/iod/home.php?s=cool+scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<div class="is-multiline"><div class="column">
              <a href="iod/scene_123.php"></a>
              <div class="has-text-weight-bold">Cool Scene</div>
              <span class="tag">March 4, 2021</span>
              <img src="https://cdn/cover.jpg" />
            </div></div>""",
        )
    )
    results: list[SearchResult] = []
    await IntersecClient().search(results, search_context(SITE, 'cool scene'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://www.insexondemand.com/iod/scene_123.php'
    assert results[0].display_date == '2021-03-04'
    detail_html = '<div class="has-text-weight-bold">Cool Scene</div>'
    respx.get('https://www.insexondemand.com/iod/scene_123.php').mock(return_value=httpx.Response(200, text=detail_html))
    detail = await IntersecClient().fetch_scene_detail(IntersecClient().decode(results[0].cur_id), SITE)
    assert detail is not None
    assert 'https://cdn/cover.jpg' in detail.art


@respx.mock
async def test_detail() -> None:
    url = 'https://www.insexondemand.com/iod/scene_123.php'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <div class="has-text-weight-bold">Cool Scene</div>
              <div class="has-text-white-ter">
                <a class="is-dark" href="/x">Jane Doe</a>
                <a class="is-dark" href="/x">John Smith</a>
                <a class="is-dark" href="https://hardtied.com/x">Channel</a>
                <span class="is-dark">March 4, 2021</span>
              </div>
              <div class="has-text-white-ter">skip</div>
              <div class="has-text-white-ter">A summary.</div>
              <video-js poster="https://cdn/poster.jpg"></video-js>
            </body></html>""",
        )
    )
    detail = await IntersecClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Intersec Interactive'
    assert detail.tagline == 'Hardtied'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['BDSM']
    assert [a.name for a in detail.actors] == ['Jane Doe', 'John Smith']
    assert detail.art == ['https://cdn/poster.jpg']
