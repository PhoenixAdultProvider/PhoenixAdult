from __future__ import annotations

from urllib.parse import quote

import httpx
import respx

from phoenixadult.clients.sites.twotgirls import TwoTGirlsClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site
from tests.support import served_collections

SITE = find_site('TwoTGirls')
assert SITE is not None


@respx.mock
async def test_search_direct_hit() -> None:
    url = 'https://twotgirls.com/video/wild-scene'
    respx.get(url).mock(return_value=httpx.Response(200, text='<html><body><div class="video-details"><h1>Wild Scene</h1></div></body></html>'))
    results: list[SearchResult] = []
    await TwoTGirlsClient().search(results, SearchContext(title='wild scene', encoded=quote('wild scene'), search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].scene_url == url
    assert results[0].title == 'Wild Scene'


@respx.mock
async def test_search_fallback_to_onsite() -> None:
    respx.get('https://twotgirls.com/video/wild-scene').mock(return_value=httpx.Response(404, text=''))
    respx.get('https://twotgirls.com/videos?query=' + quote('wild scene')).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <article>
                <a href="https://twotgirls.com/video/wild-scene-123"></a>
                <h2>Wild Scene</h2>
              </article>
            </body></html>""",
        )
    )
    results: list[SearchResult] = []
    await TwoTGirlsClient().search(results, SearchContext(title='wild scene', encoded=quote('wild scene'), search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].scene_url == 'https://twotgirls.com/video/wild-scene-123'


@respx.mock
async def test_detail() -> None:
    url = 'https://twotgirls.com/video/wild-scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1>Wild Scene</h1>
              <div class="shadow video-details"><p>A blurb.</p></div>
              <p class="video-tags"><a>Anal</a><a>Hardcore</a></p>
              <p class="video-date">
                <a href="/star/jane">Jane Doe</a>
                <a href="/star/mary">Mary Roe</a>
                <a href="/star/anna">Anna Lee</a>
              </p>
              <video poster="https://cdn/tt/poster-720p.jpg"></video>
              <article>
                <div class="row">
                  <img src="https://cdn/tt/g1.jpg" />
                  <img src="https://cdn/tt/g2.jpg" />
                </div>
              </article>
            </body></html>""",
        )
    )
    for slug, photo in (('jane', 'jane.jpg'), ('mary', 'mary.jpg'), ('anna', 'anna.jpg')):
        respx.get(f'https://twotgirls.com/star/{slug}').mock(
            return_value=httpx.Response(200, text=f'<html><body><div class="col-md-4"><img src="https://cdn/tt/{photo}" /></div></body></html>')
        )
    detail = await TwoTGirlsClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Wild Scene'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'TwoTGirls'
    assert detail.tagline == 'TwoTGirls'
    assert served_collections(detail) == ['TwoTGirls']
    assert detail.genres == ['Anal', 'Hardcore', 'Threesome']
    assert [(a.name, a.photo_url) for a in detail.actors] == [
        ('Jane Doe', 'https://cdn/tt/jane.jpg'),
        ('Mary Roe', 'https://cdn/tt/mary.jpg'),
        ('Anna Lee', 'https://cdn/tt/anna.jpg'),
    ]
    assert detail.art == ['https://cdn/tt/poster-1080p.jpg', 'https://cdn/tt/g1.jpg', 'https://cdn/tt/g2.jpg']
