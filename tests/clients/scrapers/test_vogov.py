from __future__ import annotations

from urllib.parse import quote

import httpx
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.sites.vogov import VogoVClient
from phoenixadult.registry import find_site

SITE = find_site('VogoV')
assert SITE is not None


@respx.mock
async def test_search_cards() -> None:
    url = 'https://vogov.com/search/?q=' + quote('wild scene')
    html = """<html><body>
      <div class="video-post-content">
        <a class="video-post-main" href="https://vogov.com/scene/wild">
          <img alt="Wild Scene" src="https://cdn/v.jpg" />
        </a>
        <span class="video-data float-right"><em>January 5, 2024</em></span>
      </div>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await VogoVClient().search(results, SearchContext(title='wild scene', encoded=quote('wild scene'), search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].scene_url == 'https://vogov.com/scene/wild'
    assert results[0].title == 'Wild Scene'
    assert results[0].release_date == '2024-01-05'


@respx.mock
async def test_detail() -> None:
    url = 'https://vogov.com/scene/wild'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <div class="video-page-header"><h1>Wild Scene</h1></div>
              <div class="info-video-description"><p>A blurb.</p></div>
              <ul class="list-unstyled info-video-details">
                <li><span>January 5, 2024</span></li>
                <li><span>00:30:00</span></li>
              </ul>
              <div class="info-video-category"><a>Anal</a><a>Hardcore</a></div>
              <div class="info-video-models"><a href="https://vogov.com/model/jane">Jane Doe</a></div>
              <div class="swiper-wrapper">
                <figure><a href="https://cdn/g1.jpg">g1</a></figure>
                <figure><a href="https://cdn/g2.jpg">g2</a></figure>
              </div>
            </body></html>""",
        )
    )
    respx.get('https://vogov.com/model/jane').mock(
        return_value=httpx.Response(200, text='<html><body><div class="m-images"><img src="https://cdn/jane.jpg" /></div></body></html>')
    )
    detail = await VogoVClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Wild Scene'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'VogoV'
    assert detail.tagline == ''
    assert detail.collections == ['VogoV']
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['Anal', 'Hardcore']
    assert [(a.name, a.photo_url) for a in detail.actors] == [('Jane Doe', 'https://cdn/jane.jpg')]
    assert detail.directors is not None
    assert [d.name for d in detail.directors] == ['Markus Dupree']
    assert detail.art == ['https://cdn/g1.jpg', 'https://cdn/g2.jpg']
