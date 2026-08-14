from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.aggregators.iafd import IAFDClient, supplement
from phoenixadult.clients.base import FetchCtx, SearchContext, SearchResult
from phoenixadult.registry import find_site

SITE = find_site('Black Patrol')
assert SITE is not None

LISTING_URL = 'https://www.iafd.com/distrib.rme/distrib=9954/blackpatrol.com.htm'
SCENE_URL = 'https://www.iafd.com/title.rme/id=79f12109-814d-4bc2-9812-d036686fbddf'

LISTING_HTML = """<html><body><table id="distable"><tbody>
  <tr><th>Title</th><th>Site</th><th>Year</th></tr>
  <tr><td><a href="/title.rme/id=79f12109-814d-4bc2-9812-d036686fbddf">Black Artistry Denied</a></td>
      <td>blackpatrol.com</td><td>2017</td></tr>
  <tr><td><a href="/title.rme/id=424a0cdd-84c3-4fa9-a380-d2726e2b279d">Black Male Squatting in Home</a></td>
      <td>blackpatrol.com</td><td>2016</td></tr>
</tbody></table></body></html>"""

SCENE_HTML = """<html><body>
  <h1>Black Artistry Denied (2017)</h1>
  <p class="bioheading">Release Date</p><p class="biodata">Jan 27, 2017</p>
  <p class="bioheading">Director</p><p class="biodata"><a href="/person.rme/id=1">Ric Cash</a></p>
  <div id="synopsis"><h4>Synopsis</h4><div class="padded-panel">Got a call about some graffiti.</div></div>
  <div class="castbox">
    <a href="/person.rme/id=2"><img src="https://www.iafd.com/graphics/headshots/joslynjane_f_25.jpg">Joslyn Jane</a>
    <a href="/person.rme/id=3"><img src="https://www.iafd.com/graphics/headshots/maggiegreen_f.jpg">Maggie Green</a>
  </div>
</body></html>"""


@respx.mock
async def test_search_lists_the_studio_catalogue() -> None:
    respx.get(LISTING_URL).mock(return_value=httpx.Response(200, text=LISTING_HTML))

    results: list[SearchResult] = []
    await IAFDClient().search(results, SearchContext(title='Black Artistry Denied', encoded='black+artistry', search_site=SITE.name, site_info=SITE))

    assert [r.title for r in results][0] == 'Black Artistry Denied'
    assert results[0].scene_url == SCENE_URL


@respx.mock
async def test_search_drops_entries_from_another_year() -> None:
    respx.get(LISTING_URL).mock(return_value=httpx.Response(200, text=LISTING_HTML))

    results: list[SearchResult] = []
    await IAFDClient().search(
        results,
        SearchContext(title='Black', encoded='black', search_site=SITE.name, site_info=SITE, search_date='2016-05-01'),
    )

    assert [r.title for r in results] == ['Black Male Squatting in Home']


@respx.mock
async def test_search_accepts_a_scene_id_directly() -> None:
    respx.get(SCENE_URL).mock(return_value=httpx.Response(200, text=SCENE_HTML))

    results: list[SearchResult] = []
    await IAFDClient().search(
        results,
        SearchContext(
            title='anything',
            encoded='anything',
            search_site=SITE.name,
            site_info=SITE,
            scene_id='79f12109-814d-4bc2-9812-d036686fbddf',
        ),
    )

    assert len(results) == 1
    assert results[0].title == 'Black Artistry Denied'


@respx.mock
async def test_detail_reads_every_field_iafd_carries() -> None:
    respx.get(SCENE_URL).mock(return_value=httpx.Response(200, text=SCENE_HTML))

    metadata = await IAFDClient().fetch_scene_detail(SCENE_URL, SITE)

    assert metadata is not None
    assert metadata.title == 'Black Artistry Denied'
    assert metadata.release_date == '2017-01-27'
    assert metadata.summary == 'Got a call about some graffiti.'
    assert [a.name for a in metadata.actors] == ['Joslyn Jane', 'Maggie Green']
    assert metadata.actors[0].photo_url == 'https://www.iafd.com/graphics/headshots/joslynjane_f_25.jpg'
    assert [d.name for d in metadata.directors or []] == ['Ric Cash']
    assert metadata.studio == 'Black Patrol'
    assert metadata.collections == ['Black Patrol']
    assert metadata.art == []


@respx.mock
async def test_supplement_returns_the_date_and_cast_for_a_studio_listing() -> None:
    studio_url = 'https://www.iafd.com/studio.rme/studio=9856/blackpayback.com.htm'
    respx.get(studio_url).mock(return_value=httpx.Response(200, text=LISTING_HTML.replace('distable', 'studio')))
    respx.get(SCENE_URL).mock(return_value=httpx.Response(200, text=SCENE_HTML))

    release_date, actors = await supplement(IAFDClient(), studio_url, 'Black Artistry Denied', FetchCtx(), '[test]')

    assert release_date == '2017-01-27'
    assert [a.name for a in actors] == ['Joslyn Jane', 'Maggie Green']


@respx.mock
async def test_supplement_is_quiet_when_the_title_is_not_listed() -> None:
    studio_url = 'https://www.iafd.com/studio.rme/studio=9856/blackpayback.com.htm'
    respx.get(studio_url).mock(return_value=httpx.Response(200, text=LISTING_HTML.replace('distable', 'studio')))

    assert await supplement(IAFDClient(), studio_url, 'Not On The List', FetchCtx(), '[test]') == (None, [])


@respx.mock
async def test_every_iafd_request_goes_through_the_bypass() -> None:
    studio_url = 'https://www.iafd.com/studio.rme/studio=9856/blackpayback.com.htm'
    respx.get(studio_url).mock(return_value=httpx.Response(200, text=LISTING_HTML.replace('distable', 'studio')))
    respx.get(SCENE_URL).mock(return_value=httpx.Response(200, text=SCENE_HTML))

    seen: list[bool] = []

    class SpyClient(IAFDClient):
        async def fetch_and_load(self, url, ctx=None, label=''):  # type: ignore[no-untyped-def, override]
            seen.append(bool(ctx and ctx.use_bypass))
            return await super().fetch_and_load(url, ctx, label)

    await supplement(SpyClient(), studio_url, 'Black Artistry Denied', FetchCtx(use_bypass=False), '[test]')

    assert seen == [True, True]
