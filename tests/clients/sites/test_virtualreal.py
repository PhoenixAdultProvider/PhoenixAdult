from __future__ import annotations

import json

import httpx
import respx

from phoenixadult.clients.sites.virtualreal import VirtualRealClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site
from tests.support import served_collections

SITE = find_site('VirtualRealPorn')
assert SITE is not None


def _ld(data: object) -> str:
    return f'<script type="application/ld+json">{json.dumps(data)}</script>'


@respx.mock
async def test_search_last_ld_strip_suffix() -> None:
    url = 'https://virtualrealporn.com/vr-porn-video/wild-scene'
    html = f"""<html><head>
      {_ld({'@type': 'Organization', 'name': 'irrelevant'})}
      {_ld({'name': 'Wild Scene | VirtualRealPorn', 'url': url, 'datePublished': '2024-01-05', 'actors': [{'name': 'Jane Doe'}]})}
    </head><body></body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await VirtualRealClient().search(results, SearchContext(title='wild scene', encoded='x', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Wild Scene'
    assert results[0].scene_url == url
    assert results[0].release_date == '2024-01-05'


@respx.mock
async def test_detail_actor_photo_zip() -> None:
    url = 'https://virtualrealporn.com/vr-porn-video/wild-scene'
    ld = _ld(
        {
            'name': 'Wild Scene | VirtualRealPorn',
            'description': 'A blurb.',
            'url': url,
            'datePublished': '2024-01-05',
            'keywords': 'Anal, Hardcore',
            'image': 'https://cdn.vr.com/og.jpg',
            'actors': [{'name': 'Jane Doe'}, {'name': 'Mary Roe'}],
        }
    )
    html = f"""<html><head>{ld}</head><body>
      <div class="model-box"><a><img src="https://cdn.vr.com/jane.jpg" /></a></div>
      <div class="model-box"><a><img src="https://cdn.vr.com/mary.jpg" /></a></div>
      <figure itemprop="associatedMedia"><a href="https://cdn.vr.com/g1.jpg">g1</a></figure>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    detail = await VirtualRealClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Wild Scene'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'VirtualRealPorn'
    assert detail.tagline == 'VirtualRealPorn'
    assert served_collections(detail) == ['VirtualRealPorn']
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['Anal', 'Hardcore']
    assert [(a.name, a.photo_url) for a in detail.actors] == [
        ('Jane Doe', 'https://cdn.vr.com/jane.jpg'),
        ('Mary Roe', 'https://cdn.vr.com/mary.jpg'),
    ]
    assert detail.art == ['https://cdn.vr.com/og.jpg', 'https://cdn.vr.com/g1.jpg']
