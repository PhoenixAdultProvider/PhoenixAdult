from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites.xconfessions import XConfessionsClient
from app.registry import find_site

XC = find_site('XConfessions')
LC = find_site('LustCinema')
assert XC is not None and LC is not None


@respx.mock
async def test_search_movies_plus_direct_slug() -> None:
    respx.get('https://xconfessions.com').mock(return_value=httpx.Response(200, text='<html><script>window.config = {.access_token="TOK123"};</script></html>'))
    respx.post('https://api.xconfessions.com/api/search').mock(
        return_value=httpx.Response(
            200,
            json={
                'data': [
                    {'resourceType': 'movies', 'slug': 'wild-scene', 'title': 'Wild Scene'},
                    {'resourceType': 'performers', 'slug': 'jane', 'title': 'Jane Doe'},
                ]
            },
        )
    )
    respx.get('https://api.xconfessions.com/api/movies/slug/wild-scene').mock(return_value=httpx.Response(200, json={'data': {'title': 'Wild Scene Direct'}}))
    results: list[SearchResult] = []
    await XConfessionsClient().search(results, SearchContext(title='wild scene', encoded='x', search_site=XC.name, site_info=XC))
    assert len(results) == 1
    assert results[0].title == 'Wild Scene'
    assert results[0].scene_url == 'https://api.xconfessions.com/api/movies/slug/wild-scene'


@respx.mock
async def test_search_lustcinema_token_prefix() -> None:
    respx.get('https://lustcinema.com').mock(return_value=httpx.Response(200, text='<html><script>x.access_token="LCTOK";</script></html>'))
    respx.post('https://next-prod-api.lustcinema.com/api/search').mock(
        return_value=httpx.Response(200, json={'data': [{'resourceType': 'movies', 'slug': 'lc-scene', 'title': 'LC Scene'}]})
    )
    respx.get('https://next-prod-api.lustcinema.com/api/movies/slug/lc-scene').mock(return_value=httpx.Response(404))
    results: list[SearchResult] = []
    await XConfessionsClient().search(results, SearchContext(title='lc scene', encoded='x', search_site=LC.name, site_info=LC))
    assert len(results) == 1
    assert results[0].title == 'LC Scene'


@respx.mock
async def test_detail_json_map() -> None:
    respx.get('https://xconfessions.com').mock(return_value=httpx.Response(200, text='<html><script>.access_token="TOK";</script></html>'))
    respx.get('https://api.xconfessions.com/api/movies/slug/best-compilation').mock(
        return_value=httpx.Response(
            200,
            json={
                'data': {
                    'title': 'Best Compilation',
                    'synopsis_clean': 'Selection of greatest hits.',
                    'release_date': '2024-01-05',
                    'poster_picture': 'https://cdn.xc.com/poster.jpg?v=1',
                    'rating': 4.5,
                    'producer': {'name': 'Erika', 'last_name': 'Lust', 'poster_image': 'https://cdn.xc.com/erika.jpg?t=1'},
                    'director': {'name': 'Erika', 'last_name': 'Lust'},
                    'performers': [
                        {'name': 'Jane', 'last_name': 'Doe', 'poster_image': 'https://cdn.xc.com/jane.jpg?t=2'},
                        {'name': 'Mary', 'last_name': 'Roe', 'poster_image': None},
                    ],
                    'tags': [{'title': 'Glamour'}, {'title': 'Femme'}],
                    'album': [{'path': 'https://cdn.xc.com/g1.jpg?ts=3'}, {'path': 'https://cdn.xc.com/g2.jpg'}],
                    'is_compilation': True,
                }
            },
        )
    )
    detail = await XConfessionsClient().fetch_scene_detail('best-compilation|', XC)
    assert detail is not None
    assert detail.title == 'Best Compilation'
    assert detail.summary == 'Selection of greatest hits.'
    assert detail.studio == 'Erika Lust'
    assert detail.tagline == 'XConfessions'
    assert detail.collections == ['XConfessions']
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['Glamour', 'Femme', 'Compilation']
    assert [(a.name, a.photo_url) for a in detail.actors] == [('Jane Doe', 'https://cdn.xc.com/jane.jpg'), ('Mary Roe', '')]
    assert detail.directors is not None and [d.name for d in detail.directors] == ['Erika Lust']
    assert detail.producers is not None and [(p.name, p.photo_url) for p in detail.producers] == [('Erika Lust', 'https://cdn.xc.com/erika.jpg')]
    assert detail.raw_image_urls == ['https://cdn.xc.com/poster.jpg', 'https://cdn.xc.com/g1.jpg', 'https://cdn.xc.com/g2.jpg']
