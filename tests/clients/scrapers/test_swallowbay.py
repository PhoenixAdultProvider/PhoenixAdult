from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites.swallowbay import SwallowBayClient
from app.registry import find_site

SITE = find_site('Swallow Bay')
assert SITE is not None

SCENE_HTML = """<html><head>
  <meta name="twitter:image:alt" content="Wild VR Session" />
  <meta property="og:image" content="https://cdn.example/poster.jpg" />
</head><body>
  <div class="content-desc more-desc">A blurb.</div>
  <div class="content-date">Date: 5th Jan 2024</div>
  <div class="content-models">
    <a title="Jane Doe">Jane</a>
    <a title="Mary Roe">Mary</a>
  </div>
  <div class="content-models-photos">
    <a title="Jane Doe"><span><img src="https://cdn.example/jane.jpg" /></span></a>
    <a title="Mary Roe"><span><img src="https://cdn.example/mary.jpg" /></span></a>
  </div>
  <div class="box">
    <a>VR</a>
    <a>Blowjob</a>
  </div>
</body></html>"""


@respx.mock
async def test_search_direct_url() -> None:
    respx.get('https://swallowbay.com/video/wild-vr-session.html').mock(return_value=httpx.Response(200, text=SCENE_HTML))
    results: list[SearchResult] = []
    await SwallowBayClient().search(results, SearchContext(title='Wild VR Session', encoded='Wild%20VR%20Session', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Wild VR Session'
    assert results[0].scene_url == 'https://swallowbay.com/video/wild-vr-session.html'
    assert results[0].score == 100


@respx.mock
async def test_detail() -> None:
    url = 'https://swallowbay.com/video/wild-vr-session.html'
    respx.get(url).mock(return_value=httpx.Response(200, text=SCENE_HTML))
    detail = await SwallowBayClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Wild VR Session'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'Swallow Bay'
    assert detail.tagline is None
    assert detail.collections == ['Swallow Bay']
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['VR', 'Blowjob']
    assert [(a.name, a.photo_url) for a in detail.actors] == [
        ('Jane Doe', 'https://cdn.example/jane.jpg'),
        ('Mary Roe', 'https://cdn.example/mary.jpg'),
    ]
    assert detail.art == ['https://cdn.example/poster.jpg']
