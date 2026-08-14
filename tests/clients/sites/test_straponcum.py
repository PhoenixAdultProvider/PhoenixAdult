from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.sites.straponcum import StraponCumClient
from phoenixadult.registry import find_site

SITE = find_site('Strapon Cum')
assert SITE is not None

SCENE_HTML = """<html><body>
  <div class="card">
    <h1 class="card-title">Wild Strapon</h1>
    <p class="card-text mb-2">A blurb.</p>
    <span>Posted <i class="fa-clock"></i> • January 5, 2024</span>
    <span>Featuring:</span>
    <a href="/models/jane">Jane Doe</a>
    <a href="/models/mary">Mary Roe</a>
    <a href="/models/sue">Sue Smith</a>
  </div>
  <div class="tag-cloud">
    <a>Anal</a>
    <a>Latex</a>
  </div>
  <div class="trailer"><img alt="abc123" src="thumb.jpg" /></div>
</body></html>"""


@respx.mock
async def test_search_direct_url() -> None:
    respx.get('https://straponcum.com/updates/Wild-Strapon.html').mock(return_value=httpx.Response(200, text=SCENE_HTML))
    results: list[SearchResult] = []
    await StraponCumClient().search(results, SearchContext(title='Wild Strapon', encoded='Wild%20Strapon', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Wild Strapon'
    assert results[0].scene_url == 'https://straponcum.com/updates/Wild-Strapon.html'
    assert results[0].release_date == '2024-01-05'
    assert results[0].score == 100


@respx.mock
async def test_detail() -> None:
    url = 'https://straponcum.com/updates/Wild-Strapon.html'
    respx.get(url).mock(return_value=httpx.Response(200, text=SCENE_HTML))
    for slug, photo in (('jane', 'https://cdn/jane.jpg'), ('mary', 'https://cdn/mary.jpg'), ('sue', 'https://cdn/sue.jpg')):
        respx.get(f'https://straponcum.com/models/{slug}').mock(
            return_value=httpx.Response(200, text=f'<html><body><img id="set-target-1" data-src0_1x="{photo}" /></body></html>')
        )
    detail = await StraponCumClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Wild Strapon'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'Strapon Cum'
    assert detail.tagline == 'Strapon Cum'
    assert detail.collections == ['Strapon Cum']
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['Lesbian', 'Strap-On', 'Anal', 'Latex', 'Threesome']
    assert [(a.name, a.photo_url) for a in detail.actors] == [
        ('Jane Doe', 'https://cdn/jane.jpg'),
        ('Mary Roe', 'https://cdn/mary.jpg'),
        ('Sue Smith', 'https://cdn/sue.jpg'),
    ]
    assert detail.art == [
        'https://straponcum.com/content/abc123/0.jpg',
        'https://straponcum.com/content/abc123/1.jpg',
        'https://straponcum.com/content/abc123/2.jpg',
        'https://straponcum.com/content/abc123/3.jpg',
    ]
