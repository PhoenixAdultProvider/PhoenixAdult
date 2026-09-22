from __future__ import annotations

from urllib.parse import quote

import httpx
import respx

from phoenixadult.clients.sites.stepsecrets import StepSecretsClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site

SITE = find_site('Step Secrets')
assert SITE is not None

DETAIL_HTML = """<html><body>
  <h1 class="font-cond">Wild Scene</h1>
  <div class="descripton">A scene blurb.</div>
  <p class="mb-2"><a href="/models/jane">Jane</a></p>
  <video poster="https://cdn.example/poster.jpg"></video>
  <div id="photoCarousel">
    <img src="https://cdn.example/p1.jpg" />
    <img src="https://cdn.example/p2.jpg" />
  </div>
</body></html>"""

ACTOR_HTML = """<html><body>
  <h1 class="font-cond">Jane Doe</h1>
  <div class="model-about"><img src="https://cdn.example/jane.jpg?sig=abc&exp=12345" /></div>
</body></html>"""


@respx.mock
async def test_search_cards() -> None:
    url = 'https://www.stepsecrets.com/?query=' + quote('Wild Scene')
    html = """<html><body>
      <div class="card-simple">
        <a class="color-title" href="https://www.stepsecrets.com/scene/wild-scene">Wild Scene</a>
      </div>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await StepSecretsClient().search(results, SearchContext(title='Wild Scene', encoded=quote('Wild Scene'), search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Wild Scene'
    assert results[0].scene_url == 'https://www.stepsecrets.com/scene/wild-scene'


@respx.mock
async def test_detail() -> None:
    url = 'https://www.stepsecrets.com/scene/wild-scene'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    respx.get('https://www.stepsecrets.com/models/jane').mock(return_value=httpx.Response(200, text=ACTOR_HTML))
    detail = await StepSecretsClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Wild Scene'
    assert detail.summary == 'A scene blurb.'
    assert detail.studio == 'Joymii'
    assert detail.tagline == 'Step Secrets'
    assert detail.collections == ['Step Secrets']
    assert detail.genres == ['European', 'Glamcore', 'Taboo']
    assert [a.name for a in detail.actors] == ['Jane Doe']
    assert detail.actors[0].photo_url == 'https://cdn.example/jane.jpg'
    assert detail.art == ['https://cdn.example/poster.jpg', 'https://cdn.example/p1.jpg', 'https://cdn.example/p2.jpg']
