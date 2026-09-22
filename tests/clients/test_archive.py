from __future__ import annotations

from typing import Any

from phoenixadult.clients.aggregators import archive
from phoenixadult.clients.aggregators.archive import ArchiveClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site


def _seed(site: str, cur_id: str, title: str, date: str = '', thumb: str = '') -> None:
    from phoenixadult.utils import cache as mc
    from phoenixadult.utils.cache import scene_store

    md: dict[str, Any] = {'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': title, 'studio': site}
    if date:
        md['originallyAvailableAt'] = date
    if thumb:
        md['thumb'] = thumb
    data = {'MediaContainer': {'identifier': 'i', 'size': 1, 'Metadata': [md]}}
    scene_store.upsert(site, cur_id, mc._hash(site, cur_id), f'{site.lower()}/{cur_id}', data)


def _ctx(title: str, site_name: str = 'Aussie Ass') -> SearchContext:
    site = find_site(site_name)
    assert site is not None
    return SearchContext(title=title, encoded=title, search_site=site_name, site_info=site)


async def test_archive_search_finds_a_cached_scene() -> None:
    _seed('Aussie Ass', 'QUExOTY', "Olivia's First Scene", '2014-11-15', '/cache/aussieass/abc/images/poster-00.jpg')
    _seed('Aussie Ass', 'Zm9vYmFy', 'Something Entirely Different', '2015-01-01')

    results: list[SearchResult] = []
    await ArchiveClient().search(results, _ctx("Olivia's First Scene"))

    assert results[0].cur_id == 'QUExOTY'
    assert results[0].score == 100
    assert results[0].display_date == '2014-11-15'
    assert (results[0].thumb_url or '').endswith('/cache/aussieass/abc/images/poster-00.jpg')


async def test_archive_search_only_sees_its_own_site() -> None:
    _seed('Aussie Ass', 'a1', 'Shared Title')
    _seed('Brazzers', 'b1', 'Shared Title')

    results: list[SearchResult] = []
    await ArchiveClient().search(results, _ctx('Shared Title'))

    assert [r.cur_id for r in results] == ['a1']


async def test_archive_search_caps_its_result_list() -> None:
    for n in range(archive.MAX_RESULTS + 5):
        _seed('Aussie Ass', f'c{n}', f'Scene Number {n}')

    results: list[SearchResult] = []
    await ArchiveClient().search(results, _ctx('Scene Number 3'))

    assert len(results) == archive.MAX_RESULTS
    assert results[0].title == 'Scene Number 3'


async def test_archive_search_is_empty_when_nothing_is_cached() -> None:
    results: list[SearchResult] = []
    await ArchiveClient().search(results, _ctx('Anything At All'))
    assert results == []


async def test_archive_still_never_scrapes() -> None:
    site = find_site('Aussie Ass')
    assert site is not None
    assert await ArchiveClient().fetch_scene_detail('anything', site) is None
