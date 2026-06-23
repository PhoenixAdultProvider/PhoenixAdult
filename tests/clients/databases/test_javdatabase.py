from __future__ import annotations

import httpx
import respx

from app.clients.aggregators.javdatabase import JAVDatabaseClient
from app.clients.base import SearchContext
from app.registry import find_site

SITE = find_site('JAVDatabase')
assert SITE is not None


@respx.mock
async def test_search_builds_javid_card() -> None:
    respx.get('https://www.javdatabase.com/?wpessid=391487&s=QWE-999').mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <div class="card h-100">
                <div class="mt-auto"><a>Some Movie</a></div>
                <p><a class="cut-text" href="/movies/qwe-999/">QWE-999</a></p>
              </div>
            </body></html>""",
        )
    )
    results = await JAVDatabaseClient().search(SearchContext(title='QWE 999', encoded='QWE%20999', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == '[QWE-999] Some Movie'
    assert results[0].scene_url == 'https://www.javdatabase.com/movies/qwe-999/'


@respx.mock
async def test_detail_decensor() -> None:
    url = 'https://www.javdatabase.com/movies/qwe-999/'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><head><meta property="og:title" content="QWE-999"></head><body>
              <p><b>Title: </b>The S***e Wife</p>
              <p><b>Studio: </b><span><a>Prestige</a></span></p>
              <p><b>Release Date: </b>2024-01-05</p>
              <p><b>Genre(s): </b><span><a>Drama</a></span></p>
              <div><h4>Actress/Idols</h4>
                <div class="card-body"><a class="cut-text">Jane Doe</a>
                  <div class="idol-thumb"><img src="https://cdn/thumb/jane.jpg"/></div></div>
              </div>
              <table><tr class="moviecovertb"><td><img src="https://cdn/cover.jpg"/></td></tr></table>
            </body></html>""",
        )
    )
    respx.get('https://cdn/full/jane.jpg').mock(return_value=httpx.Response(200, content=b''))
    respx.get('https://www.javbus.com/en/QWE-999').mock(return_value=httpx.Response(200, text='<html><body></body></html>'))
    detail = await JAVDatabaseClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == '[QWE-999] The Slave Wife'
    assert detail.studio == 'Prestige'
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['Drama']
    assert [(a.name, a.photo_url) for a in detail.actors] == [('Jane Doe', 'https://cdn/full/jane.jpg')]
    assert 'https://cdn/cover.jpg' in detail.raw_image_urls


@respx.mock
async def test_detail_blank_unknown_thumb() -> None:
    url = 'https://www.javdatabase.com/movies/qwe-998/'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><head><meta property="og:title" content="QWE-998"></head><body>
              <p><b>Title: </b>A Movie</p>
              <div><h4>Actress/Idols</h4>
                <div class="card-body"><a class="cut-text">Jane Doe</a>
                  <div class="idol-thumb"><img src="https://cdn/thumb/jane.jpg"/></div></div>
              </div>
            </body></html>""",
        )
    )
    respx.get('https://cdn/full/jane.jpg').mock(return_value=httpx.Response(302, headers={'Location': 'https://cdn/unknown.jpg'}))
    respx.get('https://cdn/unknown.jpg').mock(return_value=httpx.Response(200, content=b''))
    respx.get('https://www.javbus.com/en/QWE-998').mock(return_value=httpx.Response(200, text='<html><body></body></html>'))
    detail = await JAVDatabaseClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert [(a.name, a.photo_url) for a in detail.actors] == [('Jane Doe', '')]
