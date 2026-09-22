from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.networks.adultprime import AdultPrimeClient, __testing__
from phoenixadult.models.scrape import SearchResult
from phoenixadult.registry import find_site
from tests.support import search_context

SITE = find_site('Adult Prime')
SWEETHEARTS = find_site('Club Sweethearts')
assert SITE is not None and SWEETHEARTS is not None


@respx.mock
async def test_search_keyword_video_and_performer() -> None:
    row = """<ul id="studio-videos-container"><li>
      <span class="video-title">Cool Scene</span>
      <div class="overlay inline-preview" data-id="9001"></div>
      <span class="releasedate">Aug 27, 2020</span>
    </li></ul>"""
    respx.get('https://adultprime.com/studios/search?type=video&q=cool+scene').mock(return_value=httpx.Response(200, text=row))
    respx.get('https://adultprime.com/studios/search?type=performer&q=cool+scene').mock(
        return_value=httpx.Response(200, text='<ul id="studio-videos-container"></ul>')
    )
    results: list[SearchResult] = []
    await AdultPrimeClient().search(results, search_context(SITE, 'cool scene', search_date='2020-08-27', space='%20'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://adultprime.com/studios/video/9001'
    assert results[0].display_date == '2020-08-27'


@respx.mock
async def test_search_direct_scene_id() -> None:
    url = 'https://adultprime.com/studios/video/555'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<h1>Studio: Cool Scene Full video by Someone</h1>
            <p class="update-info-line regular"><b>Studio:</b><a>BBvideo</a></p>
            <p class="update-info-line regular"><i class="fa calendar"></i><b>27.08.2020</b></p>""",
        )
    )
    results: list[SearchResult] = []
    await AdultPrimeClient().search(results, search_context(SITE, 'cool scene', scene_id='555', space='%20'))
    assert len(results) == 1
    assert results[0].scene_url == url
    assert results[0].title == 'Cool Scene'
    assert results[0].score == 100
    assert results[0].display_date == '2020-08-27'


@respx.mock
async def test_detail_fields() -> None:
    url = 'https://adultprime.com/studios/video/9001'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1>BBvideo: Cool Scene Full video by Someone</h1>
              <p class="description">A genuine summary.</p>
              <p class="update-info-line regular"><b>Studio:</b> <a>BBvideo</a></p>
              <p class="update-info-line regular"><b>Niches:</b> Anal, Gonzo, MILF</p>
              <p class="update-info-line regular"><b>Performer:</b> <a>Jane Doe</a><a>John Smith</a></p>
              <p class="update-info-line regular"><i class="fa calendar"></i><b>27.08.2020</b></p>
              <video id="v1" poster="https://cdn.example.com/p.jpg?token=abc"></video>
            </body></html>""",
        )
    )
    respx.get('https://adultprime.com/studios/search?type=performer&q=Jane+Doe').mock(
        return_value=httpx.Response(
            200, text='<div class="performer-container"><div class="ratio-square" style="background-image:url(https://cdn/jane.jpg)"></div></div>'
        )
    )
    respx.get('https://adultprime.com/studios/search?type=performer&q=John+Smith').mock(return_value=httpx.Response(200, text='<div></div>'))
    detail = await AdultPrimeClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A genuine summary.'
    assert detail.studio == 'Adult Prime'
    assert detail.tagline == 'BBvideo'
    assert detail.collections == ['BBvideo']
    assert detail.release_date == '2020-08-27'
    assert detail.genres == ['Anal', 'Gonzo', 'MILF']
    assert [a.name for a in detail.actors] == ['Jane Doe', 'John Smith']
    assert detail.actors[0].photo_url == 'https://cdn/jane.jpg'
    assert detail.art == ['https://cdn.example.com/p.jpg?token=abc']


@respx.mock
async def test_detail_skips_generic_summary_and_studio_override() -> None:
    url = 'https://adultprime.com/studios/video/42'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1>Cool Scene</h1>
              <p class="description">Welcome to FreshPOV.com videos and more boilerplate.</p>
            </body></html>""",
        )
    )
    detail = await AdultPrimeClient().fetch_scene_detail(url, SWEETHEARTS)
    assert detail is not None
    assert detail.summary == ''
    assert detail.studio == 'Club Sweethearts'


def test_helpers() -> None:
    assert __testing__['parse_euro_date']('27.08.2020') == '2020-08-27'
    assert __testing__['parse_euro_date']('no date') is None
    assert __testing__['clean_title']('BBvideo: Cool Scene Full video by Someone') == 'Cool Scene'
    assert __testing__['studio_for']('Club Sweethearts') == 'Club Sweethearts'
    assert __testing__['studio_for']('Adult Prime') == 'Adult Prime'
