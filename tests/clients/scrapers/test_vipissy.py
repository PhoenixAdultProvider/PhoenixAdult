from __future__ import annotations

from urllib.parse import quote

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites.vipissy import VIPissyClient
from app.registry import find_site

SITE = find_site('VIPissy')
assert SITE is not None

DETAIL_HTML = """<html><body><div>
  <section><div><div><img src="https://cdn.vp.com/cover.jpg" /></div></div></section>
  <section>
    <dl>
      <dd>
        <a href="/models/jane">Jane Doe</a>
        <a href="/models/mary">Mary Roe</a>
        <a href="/models/anna">Anna Lee</a>
      </dd>
      <dd>Jan 5, 2024</dd>
    </dl>
  </section>
  <section></section>
  <section>
    <div>
      Full summary text here.
      <p><a>Tag1</a><a>Tag2</a></p>
      Show more...
    </div>
  </section>
</div>
<section class="downloads"><strong>Wild Scene</strong></section>
<div id="pics2"><div><ul><li><div><div><img src="https://cdn.vp.com/g1.jpg" /></div></div></li></ul></div></div>
</body></html>"""


def _actor_page(photo: str) -> str:
    return f'<html><body><div><section><div><div><img src="{photo}" /></div></div></section></div></body></html>'


@respx.mock
async def test_search_cards() -> None:
    url = 'https://www.vipissy.com/updates?search=' + quote('wild scene')
    html = """<html><body>
      <div style="position:relative; background:black;">
        <a title="Wild Scene" href="/updates/wild-scene-1234"></a>
        <span class="date">January 5, 2024</span>
      </div>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await VIPissyClient().search(results, SearchContext(title='wild scene', encoded=quote('wild scene'), search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Wild Scene'
    assert results[0].scene_url == 'https://www.vipissy.com/updates/wild-scene-1234'
    assert results[0].release_date == '2024-01-05'


@respx.mock
async def test_detail() -> None:
    url = 'https://www.vipissy.com/updates/wild-scene-1234/'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    for slug, photo in (('jane', 'jane.jpg'), ('mary', 'mary.jpg'), ('anna', 'anna.jpg')):
        respx.get(f'https://www.vipissy.com/models/{slug}').mock(return_value=httpx.Response(200, text=_actor_page(f'https://cdn.vp.com/{photo}')))
    detail = await VIPissyClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Wild Scene'
    assert detail.summary == 'Full summary text here.'
    assert detail.studio == 'VIPissy'
    assert detail.tagline == 'VIPissy'
    assert detail.collections == ['VIPissy']
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['tag1', 'tag2', 'Threesome']
    assert [(a.name, a.photo_url) for a in detail.actors] == [
        ('Jane Doe', 'https://cdn.vp.com/jane.jpg'),
        ('Mary Roe', 'https://cdn.vp.com/mary.jpg'),
        ('Anna Lee', 'https://cdn.vp.com/anna.jpg'),
    ]
    assert detail.raw_image_urls == ['https://media.vipissy.com/videos/wild-scene-1234/cover/l.jpg', 'https://cdn.vp.com/g1.jpg']
