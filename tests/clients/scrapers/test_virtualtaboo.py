from __future__ import annotations

from urllib.parse import quote

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites.virtualtaboo import VirtualTabooClient
from app.registry import find_site

SITE = find_site('VirtualTaboo')
assert SITE is not None


def _card(href: str, title: str, actors: str) -> str:
    return f"""
      <div class="video-card__item">
        <a class="image-container" href="{href}"><img alt="{title}"></a>
        <div class="video-card__description">
          <a href="{href}" class="video-card__title">{title}</a>
          <div class="video-card__actors"><a href="/pornstars/x">{actors}</a></div>
        </div>
      </div>"""


@respx.mock
async def test_search_cards() -> None:
    url = 'https://virtualtaboo.com/search?q=' + quote('wild scene')
    html = f'<html><body>{_card("/videos/wild-scene-vt1", "wild scene", "Jane Doe")}{_card("/videos/other-vt2", "Other", "Mary Roe")}</body></html>'
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    respx.get('https://virtualtaboo.com/pornstars/wild-scene').mock(return_value=httpx.Response(404))
    results: list[SearchResult] = []
    await VirtualTabooClient().search(results, SearchContext(title='wild scene', encoded=quote('wild scene'), search_site=SITE.name, site_info=SITE))
    assert len(results) == 2
    assert results[0].scene_url == 'https://virtualtaboo.com/videos/wild-scene-vt1'
    assert results[0].title == 'wild scene'


@respx.mock
async def test_search_merges_model_page_for_actress_names() -> None:
    search_url = 'https://virtualtaboo.com/search?q=' + quote('caomei bala')
    junk = f'<html><body>{_card("/videos/jingle-balls-vtef", "Jingle Balls and Christmas Hoes", "Rebecca Black")}</body></html>'
    respx.get(search_url).mock(return_value=httpx.Response(200, text=junk))
    model_html = f'<html><body>{_card("/videos/adultery-vt7l", "Adultery in Front of Sleeping Wife", "Caomei Bala")}</body></html>'
    respx.get('https://virtualtaboo.com/pornstars/caomei-bala').mock(return_value=httpx.Response(200, text=model_html))

    results: list[SearchResult] = []
    await VirtualTabooClient().search(results, SearchContext(title='caomei bala', encoded=quote('caomei bala'), search_site=SITE.name, site_info=SITE))
    by_url = {r.scene_url: r for r in results}
    her_scene = by_url['https://virtualtaboo.com/videos/adultery-vt7l']
    junk_scene = by_url['https://virtualtaboo.com/videos/jingle-balls-vtef']
    assert her_scene.score == 90.0
    assert her_scene.score > junk_scene.score


@respx.mock
async def test_detail_full_summary() -> None:
    url = 'https://virtualtaboo.com/movie/123/wild-scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <div class="right-info">
                <h1>wild scene</h1>
                <div class="info"><a>Jane Doe</a><a>Mary Roe</a></div>
              </div>
              <div class="info mt-5">17 min • January 5, 2024</div>
              <div class="description"><span class="full">Full description text.</span></div>
              <div class="tag-list"><a>Anal</a></div>
              <div class="tag-list"><a>Hardcore</a></div>
              <meta property="og:image" content="https://cdn.vt.com/og.jpg?token=x" />
              <div class="gallery-item"><a href="https://cdn.vt.com/g1.jpg?ts=1">g1</a></div>
            </body></html>""",
        )
    )
    detail = await VirtualTabooClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'wild scene'
    assert detail.summary == 'Full description text.'
    assert detail.studio == 'VirtualTaboo'
    assert detail.tagline == 'VirtualTaboo'
    assert detail.collections == ['VirtualTaboo']
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['Anal', 'Hardcore']
    assert [a.name for a in detail.actors] == ['Jane Doe', 'Mary Roe']
    assert detail.art == ['https://cdn.vt.com/og.jpg', 'https://cdn.vt.com/g1.jpg']


@respx.mock
async def test_detail_summary_fallback() -> None:
    url = 'https://virtualtaboo.com/movie/789/fallback'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <div class="right-info"><h1>Fallback</h1></div>
              <div class="info mt-5">12 min • February 2, 2024</div>
              <details class="description">Details-only summary.</details>
            </body></html>""",
        )
    )
    detail = await VirtualTabooClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.summary == 'Details-only summary.'
    assert detail.release_date == '2024-02-02'
