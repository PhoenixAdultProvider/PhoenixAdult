from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites.xsinsvr import XSinsVRClient
from app.registry import find_site

SITE = find_site('SinsVR')
assert SITE is not None


@respx.mock
async def test_search_cards() -> None:
    url = 'https://www.xsinsvr.com/search/wild scene'
    html = """<html><body>
      <div class="tn-video tn-video--horizontal">
        <a class="tn-video-media" href="/scene/wild">x</a>
        <div><a class="tn-video-name">Wild Scene</a></div>
      </div>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await XSinsVRClient().search(results, SearchContext(title='wild scene', encoded='x', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Wild Scene'
    assert results[0].scene_url == 'https://www.xsinsvr.com/scene/wild'


@respx.mock
async def test_detail() -> None:
    url = 'https://www.xsinsvr.com/scene/wild'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><head><title>Wild Scene • SinsVR</title></head><body>
              <li><div class="small"><p>Para 1.</p></div></li>
              <li><div class="small"><p> Para 2.</p></div></li>
              <span><time>Jan 5, 2024</time></span>
              <div class="tags-item">VR</div>
              <div class="tags-item">POV</div>
              <div>
                <strong>Starring</strong>
                <span><a class="tiny-link" href="https://www.xsinsvr.com/model/jane">Jane Doe</a></span>
              </div>
              <div class="tn-photo__container">
                <div><a><div><img src="https://cdn.svr.com/g1-sceneGallerySmall.jpg" /></div></a></div>
              </div>
              <dl8-video poster="https://cdn.svr.com/poster.jpg"></dl8-video>
            </body></html>""",
        )
    )
    respx.get('https://www.xsinsvr.com/model/jane').mock(
        return_value=httpx.Response(200, text='<html><body><div class="model-header__photo"><img src="https://cdn.svr.com/jane.jpg" /></div></body></html>')
    )
    detail = await XSinsVRClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Wild Scene'
    assert detail.summary == 'Para 1. Para 2.'
    assert detail.studio == 'SinsVR'
    assert detail.tagline is None
    assert detail.collections == ['SinsVR']
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['VR', 'POV']
    assert [(a.name, a.photo_url) for a in detail.actors] == [('Jane Doe', 'https://cdn.svr.com/jane.jpg')]
    assert detail.raw_image_urls == ['https://cdn.svr.com/g1-sceneGallery.jpg', 'https://cdn.svr.com/poster.jpg']
