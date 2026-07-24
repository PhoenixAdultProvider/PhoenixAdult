from __future__ import annotations

from urllib.parse import quote

import httpx
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.sites.wearehairy import WeAreHairyClient
from phoenixadult.registry import find_site

SITE = find_site('We Are Hairy')
assert SITE is not None


@respx.mock
async def test_search_cards() -> None:
    url = 'https://www.wearehairy.com/search/?query=' + quote('wild scene')
    html = """<html><body>
      <div class="results"><ul><li>
        <p class="title"><a>Wild Scene</a></p>
        <div class="top"><p><a href="/scene/wild">x</a></p></div>
        <p class="short">Added: Jan 5, 2024</p>
      </li></ul></div>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await WeAreHairyClient().search(results, SearchContext(title='wild scene', encoded=quote('wild scene'), search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Wild Scene'
    assert results[0].scene_url == 'https://www.wearehairy.com/scene/wild'
    assert results[0].release_date == '2024-01-05'


@respx.mock
async def test_detail() -> None:
    url = 'https://www.wearehairy.com/scene/wild'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><head><title>Wild Scene</title></head><body>
              <div class="desc">
                <div><p>A blurb.</p></div>
                <div><p>Ace Director</p></div>
              </div>
              <span class="added"><time>Jan 5, 2024</time></span>
              <div class="tagline"><p><a>Hairy Armpits</a><a>Solo</a></p></div>
              <div class="meet">
                <a><img alt="Jane Doe WeAreHairy.com" /></a>
                <a><img alt="Mary Roe" /></a>
              </div>
              <div class="moviemain"><div><a><img src="//cdn.wh.com/poster.jpg" /></a></div></div>
            </body></html>""",
        )
    )
    detail = await WeAreHairyClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Wild Scene'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'We Are Hairy'
    assert detail.tagline == 'We Are Hairy'
    assert detail.collections == ['We Are Hairy']
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['Hairy Armpits', 'Solo', 'Hairy Girls', 'Hairy Pussy']
    assert [a.name for a in detail.actors] == ['Jane Doe', 'Mary Roe']
    assert detail.directors is not None and [d.name for d in detail.directors] == ['Ace Director']
    assert detail.art == ['https://cdn.wh.com/poster.jpg']
