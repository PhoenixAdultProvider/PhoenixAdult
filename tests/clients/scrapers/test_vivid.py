from __future__ import annotations

from urllib.parse import quote

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites.vivid import VividClient
from app.registry import find_site

SITE = find_site('Vivid')
assert SITE is not None


@respx.mock
async def test_search_fans_videos_and_dvds() -> None:
    q = quote('wild scene')
    respx.get(f'https://www.vivid.com/videos/api/?flagType=video&search={q}').mock(
        return_value=httpx.Response(
            200,
            json={
                'responseData': [
                    {
                        'name': 'Wild Scene',
                        'url': 'https://www.vivid.com/scenes/wild-scene',
                        'release_date': '2024-01-05',
                        'placard_800': 'https://cdn.vivid.com/wild-scene/p.jpg',
                        'site': {'name': 'Indie'},
                    }
                ]
            },
        )
    )
    respx.get(f'https://www.vivid.com/dvds/api/?flagType=video&search={q}').mock(
        return_value=httpx.Response(
            200,
            json={
                'responseData': [
                    {
                        'name': 'DVD Compilation',
                        'url': 'https://www.vivid.com/dvds/compilation',
                        'release_date': '2024-02-10',
                        'placard_800': 'https://cdn.vivid.com/comp/p.jpg',
                    }
                ]
            },
        )
    )
    results: list[SearchResult] = []
    await VividClient().search(results, SearchContext(title='wild scene', encoded=q, search_site=SITE.name, site_info=SITE))
    assert len(results) == 2
    assert results[0].scene_url == 'https://www.vivid.com/scenes/wild-scene'
    assert results[0].release_date == '2024-01-05'
    assert results[0].subsite == 'Indie'
    assert results[1].scene_url == 'https://www.vivid.com/dvds/compilation'
    assert results[1].release_date == '2024-02-10'
    assert results[1].subsite is None


@respx.mock
async def test_detail_unpacks_extras() -> None:
    scene_url = 'https://www.vivid.com/scenes/wild-scene'
    poster = 'https://cdn.vivid.com/wild-scene/p.jpg'
    respx.get(scene_url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h2 class="scene-h2-heading">Wild Scene</h2>
              <p class="indie-model-p">A wild scene blurb.</p>
              <h5>Released: Jan 5, 2024</h5>
              <h5>Categories: <a>Anal</a><a>Hardcore</a></h5>
              <h4>Starring: <a>Jane Doe</a><a>Mary Roe</a></h4>
            </body></html>""",
        )
    )
    detail = await VividClient().fetch_scene_detail(f'{scene_url}|2024-01-05|Indie|{poster}', SITE)
    assert detail is not None
    assert detail.title == 'Wild Scene'
    assert detail.summary == 'A wild scene blurb.'
    assert detail.studio == 'Vivid Entertainment'
    assert detail.tagline == 'Indie'
    assert detail.collections == ['Indie']
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['Anal', 'Hardcore']
    assert [a.name for a in detail.actors] == ['Jane Doe', 'Mary Roe']
    assert detail.art == [poster]


@respx.mock
async def test_detail_subsite_fallback() -> None:
    scene_url = 'https://www.vivid.com/dvds/no-subsite'
    respx.get(scene_url).mock(
        return_value=httpx.Response(200, text='<html><body><h2 class="scene-h2-heading">Title</h2><p class="indie-model-p">Blurb.</p></body></html>')
    )
    detail = await VividClient().fetch_scene_detail(f'{scene_url}|||', SITE)
    assert detail is not None
    assert detail.tagline == 'Vivid'
    assert detail.art == []
