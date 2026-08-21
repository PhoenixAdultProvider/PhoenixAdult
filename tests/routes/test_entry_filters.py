from __future__ import annotations

from phoenixadult.routes.metadata_cache_routes import _SCOPE_FIELDS, EntryFilters
from tests.conftest import authed_client


def test_an_unknown_sort_falls_back_instead_of_reaching_sql() -> None:
    assert EntryFilters(sort='; DROP TABLE scenes').sort == 'updated_at'
    assert EntryFilters(direction='sideways').direction == 'desc'


def test_scope_carries_every_filter_plus_the_duplicate_paths() -> None:
    scope = EntryFilters(studio='Vixen', genre='Anal').scope(['a/b'])
    assert scope['studio'] == 'Vixen' and scope['genre'] == 'Anal'
    assert scope['dup_paths'] == ['a/b']
    assert set(scope) == {*_SCOPE_FIELDS, 'dup_paths'}


def test_the_query_alias_still_works_over_http() -> None:
    client = authed_client()
    assert client.get('/metadata/entries', params={'q': 'wild', 'dir': 'asc', 'studio': 'Vixen'}).status_code == 200


def test_out_of_range_values_are_rejected_by_validation() -> None:
    client = authed_client()
    assert client.get('/metadata/entries', params={'dups': 5}).status_code == 422
    assert client.get('/metadata/entries', params={'limit': 99999}).status_code == 422
    assert client.get('/metadata/entries', params={'offset': -1}).status_code == 422
