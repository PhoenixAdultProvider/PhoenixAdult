from __future__ import annotations

from urllib.parse import quote

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites.xevunleashed import XevUnleashedClient
from app.registry import find_site

SITE = find_site('Xev Unleashed')
assert SITE is not None
XEV_PHOTO = 'https://xevunleashed.com/content//contentthumbs/00/01/1-set-2x.jpg'


@respx.mock
async def test_search_direct_plus_onsite_dedup() -> None:
    direct_url = 'https://xevunleashed.com/updates/wild-scene.html'
    respx.get(direct_url).mock(
        return_value=httpx.Response(
            200,
            text='<html><body><span class="update_title">Wild Scene</span><span class="availdate">01/05/2024<br>added</span></body></html>',
        )
    )
    respx.get('https://xevunleashed.com/search.php?query=' + quote('wild scene')).mock(
        return_value=httpx.Response(
            200,
            text=f"""<html><body>
              <div class="updateItem"><a href="{direct_url}"></a><h4>Wild Scene Dup</h4><p><span>Jan 5, 2024</span></p></div>
              <div class="updateItem"><a href="https://xevunleashed.com/updates/other.html"></a><h4>Other Scene</h4><p><span>Feb 10, 2024</span></p></div>
            </body></html>""",
        )
    )
    results: list[SearchResult] = []
    await XevUnleashedClient().search(results, SearchContext(title='wild scene', encoded=quote('wild scene'), search_site=SITE.name, site_info=SITE))
    assert len(results) == 2
    assert results[0].scene_url == direct_url
    assert results[0].release_date == '2024-01-05'
    assert results[1].scene_url == 'https://xevunleashed.com/updates/other.html'


@respx.mock
async def test_detail_with_princess_leia() -> None:
    url = 'https://xevunleashed.com/updates/leia.html'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><head><meta name="keywords" content="Princess Leia, cosplay, sci-fi" /></head><body>
              <span class="update_title">Leia Cosplay</span>
              <span class="latest_update_description">Star Wars themed.</span>
              <span class="availdate">01/05/2024<br>Released</span>
              <span class="update_tags"><a>Cosplay</a><a>Sci-Fi</a></span>
              <div class="update_image"><img src0_4x="/content/poster.jpg" /></div>
            </body></html>""",
        )
    )
    detail = await XevUnleashedClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Leia Cosplay'
    assert detail.summary == 'Star Wars themed.'
    assert detail.studio == 'Xev Unleashed'
    assert detail.tagline is None
    assert detail.collections == ['Xev Unleashed']
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['Cosplay', 'Sci-Fi']
    assert [(a.name, a.photo_url) for a in detail.actors] == [('Xev Bellringer', XEV_PHOTO), ('Princess Leia', '')]
    assert detail.art == ['https://xevunleashed.com/content/poster.jpg']


@respx.mock
async def test_detail_no_princess_leia() -> None:
    url = 'https://xevunleashed.com/updates/regular.html'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text='<html><head><meta name="keywords" content="cosplay" /></head><body><span class="update_title">Regular Scene</span></body></html>',
        )
    )
    detail = await XevUnleashedClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert [(a.name, a.photo_url) for a in detail.actors] == [('Xev Bellringer', XEV_PHOTO)]
