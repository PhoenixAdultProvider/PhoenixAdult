from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.sites.watch4beauty import Watch4BeautyClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site

SITE = find_site('Watch4Beauty')
assert SITE is not None
B = 'https://www.watch4beauty.com'


@respx.mock
async def test_search_first_word_candidate() -> None:
    respx.get(f'{B}/api/models/jane/updates').mock(
        return_value=httpx.Response(
            200, json=[{'Issues': [{'issue_title': 'Wild Scene', 'issue_simple_title': 'wild-scene', 'issue_datetime': '2024-01-05T12:30:00Z'}]}]
        )
    )
    results: list[SearchResult] = []
    await Watch4BeautyClient().search(results, SearchContext(title='jane scene', encoded='x', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Wild Scene'
    assert results[0].release_date == '2024-01-05'
    assert results[0].scene_url == f'{B}/api/issues/wild-scene'


@respx.mock
async def test_search_veronica_special_case() -> None:
    respx.get(f'{B}/api/models/veronica-da-souza/updates').mock(
        return_value=httpx.Response(
            200, json=[{'Issues': [{'issue_title': 'Veronica Scene', 'issue_simple_title': 'veronica-scene', 'issue_datetime': '2024-02-10T09:00:00Z'}]}]
        )
    )
    results: list[SearchResult] = []
    await Watch4BeautyClient().search(results, SearchContext(title='Veronica Da Souza', encoded='x', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Veronica Scene'


@respx.mock
async def test_search_fallback_scene_models_lookup() -> None:
    respx.get(f'{B}/api/models/unknown/updates').mock(return_value=httpx.Response(200, json=[]))
    respx.get(f'{B}/api/models/unknown-scene/updates').mock(return_value=httpx.Response(200, json=[]))
    respx.get(f'{B}/api/issues/unknown-scene/models').mock(return_value=httpx.Response(200, json=[{'Models': [{'model_simple_nickname': 'realmodel'}]}]))
    respx.get(f'{B}/api/models/realmodel/updates').mock(
        return_value=httpx.Response(
            200, json=[{'Issues': [{'issue_title': 'Real Scene', 'issue_simple_title': 'real-scene', 'issue_datetime': '2024-03-15T10:00:00Z'}]}]
        )
    )
    results: list[SearchResult] = []
    await Watch4BeautyClient().search(results, SearchContext(title='unknown scene', encoded='x', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Real Scene'


@respx.mock
async def test_detail_end_to_end_json() -> None:
    respx.get(f'{B}/api/issues/wild-scene').mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    'issue_title': 'Wild Scene',
                    'issue_simple_title': 'wild-scene',
                    'issue_text': 'A wild blurb.',
                    'issue_datetime': '2024-01-05T12:30:00Z',
                    'issue_tags': 'Solo, Glamour, Outdoor',
                }
            ],
        )
    )
    respx.get(f'{B}/api/issues/wild-scene/models').mock(
        return_value=httpx.Response(
            200,
            json=[
                {'Models': [{'model_nickname': 'Jane Doe', 'model_simple_nickname': 'jane'}, {'model_nickname': 'Mary Roe', 'model_simple_nickname': 'mary'}]}
            ],
        )
    )
    detail = await Watch4BeautyClient().fetch_scene_detail('jane|wild-scene|2024-01-05', SITE)
    assert detail is not None
    assert detail.title == 'Wild Scene'
    assert detail.summary == 'A wild blurb.'
    assert detail.studio == 'Watch4Beauty'
    assert detail.tagline == ''
    assert detail.collections == ['Watch4Beauty']
    assert detail.release_date == '2024-01-05'
    assert detail.year == 2024
    assert detail.genres == ['Solo', 'Glamour', 'Outdoor']
    assert detail.directors is not None and [d.name for d in detail.directors] == ['Mark']
    assert [(a.name, a.photo_url) for a in detail.actors] == [
        ('Jane Doe', f'{ART}20240105model-jane-320.jpg'),
        ('Mary Roe', f'{ART}20240105model-mary-320.jpg'),
    ]
    assert detail.art == [
        f'{ART}20240105-issue-cover-1280.jpg',
        f'{ART}20240105-issue-video-cover-2560.jpg',
        f'{ART}20240105-issue-cover-wide-2560.jpg',
        f'{ART}model-jane-wide-2560.jpg',
        f'{ART}model-jane-1280.jpg',
        f'{ART}model-mary-wide-2560.jpg',
        f'{ART}model-mary-1280.jpg',
    ]


ART = 'https://mh-c75c2d6726.watch4beauty.com/production/'
