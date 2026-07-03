from __future__ import annotations

from urllib.parse import quote

import httpx
import respx

from app.clients.aggregators.javbus import JavBusClient
from app.clients.base import SearchContext
from app.registry import find_site

SITE = find_site('JavBus')
assert SITE is not None
DETAIL_URL = 'https://www.javbus.com/en/ABP-123'


@respx.mock
async def test_search_censored_cards() -> None:
    respx.get('https://www.javbus.com/en/search/' + quote('amazing scene')).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <a class="movie-box" href="https://www.javbus.com/en/XYZ-007">
                <div class="photo-frame"><img src="/pics/thumb/xyz.jpg" /></div>
                <div class="photo-info"><span>Amazing Scene<date>XYZ-007</date><date>2024-02-09</date></span></div>
              </a>
            </body></html>""",
        )
    )
    respx.get('https://www.javbus.com/en/uncensored/search/' + quote('amazing scene')).mock(return_value=httpx.Response(200, text='<html></html>'))
    results = await JavBusClient().search(SearchContext(title='amazing scene', encoded=quote('amazing scene'), search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == '[Censored][XYZ-007] Amazing Scene'
    assert results[0].scene_url == 'https://www.javbus.com/en/XYZ-007'
    assert results[0].score == 100


@respx.mock
async def test_search_direct_javid() -> None:
    respx.get('https://www.javbus.com/en/search/SONE-555').mock(return_value=httpx.Response(200, text='<html></html>'))
    respx.get('https://www.javbus.com/en/uncensored/search/SONE-555').mock(return_value=httpx.Response(200, text='<html></html>'))
    respx.get('https://www.javbus.com/en/SONE-555').mock(
        return_value=httpx.Response(200, text='<html><head><title>SONE-555 Direct Hit - JavBus</title></head><body></body></html>')
    )
    results = await JavBusClient().search(SearchContext(title='SONE 555', encoded=quote('SONE 555'), search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == '[Direct][SONE-555] SONE-555 Direct Hit'
    assert results[0].scene_url == 'https://www.javbus.com/en/SONE-555'
    assert results[0].score == 100


@respx.mock
async def test_detail() -> None:
    respx.get(DETAIL_URL).mock(
        return_value=httpx.Response(
            200,
            text="""<html><head><title>ABP-123 Some Scene Title - JavBus</title></head><body>
              <p><span class="header">Studio:</span><a href="/en/studio/s1">Big Studio</a></p>
              <p><span class="header">Label:</span><a href="/en/label/l1">Cool Label</a></p>
              <p><span class="header">Series:</span><a href="/en/series/sr1">Hot Series</a></p>
              <p><span class="header">Director:</span><a href="/en/director/d1">The Director</a></p>
              <div class="col-md-3 info">
                <p><span class="header">ID:</span> ABP-123</p>
                <p><span class="header">Release Date:</span> 2024-01-05</p>
              </div>
              <span class="genre"><a href="/en/genre/g1">Drama</a></span>
              <span class="genre"><a href="/en/genre/g2">Solo</a></span>
              <a class="avatar-box" href="/en/star/a1"><div class="photo-frame"><img src="/pics/actress/a1.jpg" title="Jane Doe"></div></a>
              <a class="avatar-box" href="/en/star/a2"><div class="photo-frame"><img src="/pics/actress/nowprinting.gif" title="John Roe"></div></a>
              <a class="bigImage" href="/pics/cover/abc_b.jpg"><img src="/pics/cover/abc_b.jpg"></a>
              <a class="sample-box" href="/pics/sample/abc_1.jpg"><img src="/pics/sample/abc_1.jpg"></a>
            </body></html>""",
        )
    )
    detail = await JavBusClient().fetch_scene_detail(DETAIL_URL, SITE)
    assert detail is not None
    assert detail.title == '[ABP-123] Some Scene Title'
    assert detail.studio == 'Big Studio'
    assert detail.tagline == 'Cool Label'
    assert detail.collections == ['Cool Label']
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['drama', 'solo']
    assert [(a.name, a.photo_url) for a in detail.actors] == [('Jane Doe', 'https://www.javbus.com/pics/actress/a1.jpg'), ('John Roe', '')]
    assert detail.directors is not None and [d.name for d in detail.directors] == ['The Director']
    assert detail.raw_image_urls == [
        'https://www.javbus.com/pics/cover/abc_b.jpg',
        'https://www.javbus.com/pics/sample/abc_1.jpg',
        'https://www.javbus.com/pics/thumb/abc.jpg',
    ]
