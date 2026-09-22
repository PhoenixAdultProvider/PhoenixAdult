from __future__ import annotations

from typing import Any

from phoenixadult.utils.cache.locks import apply_locks, carry_emptied_fields


def _stored(**md: Any) -> dict[str, Any]:
    return {'MediaContainer': {'Metadata': [md]}}


def test_a_locked_field_keeps_the_stored_value() -> None:
    meta = {'title': 'Scraped Title', 'summary': 'Scraped blurb'}
    held = apply_locks(meta, _stored(title='My Title', summary='Scraped blurb'), {'fields': ['title']})
    assert meta['title'] == 'My Title', 'the lock is the whole point'
    assert meta['summary'] == 'Scraped blurb', 'an unlocked field still takes the scrape'
    assert held == ['title']


def test_locking_a_field_the_snapshot_never_had_removes_it() -> None:
    meta = {'title': 'Scraped Title', 'tagline': 'Scraped'}
    apply_locks(meta, _stored(title='Kept'), {'fields': ['tagline']})
    assert 'tagline' not in meta, 'locked-but-absent means the user cleared it, not that the scrape wins'


def test_no_previous_snapshot_means_nothing_is_held() -> None:
    meta = {'title': 'Scraped'}
    assert apply_locks(meta, None, {'fields': ['title']}) == []
    assert meta['title'] == 'Scraped'


def test_an_empty_metadata_list_reads_as_a_cleared_snapshot() -> None:
    meta = {'title': 'Scraped'}
    held = apply_locks(meta, {'MediaContainer': {'Metadata': []}}, {'fields': ['title']})
    assert held == ['title']
    assert 'title' not in meta, 'an empty snapshot is treated as cleared, so the lock drops the field'


def test_an_empty_scrape_keeps_the_stored_list() -> None:
    meta: dict[str, Any] = {'Genre': []}
    carried = carry_emptied_fields(meta, _stored(Genre=[{'tag': 'Anal'}]))
    assert carried == ['Genre(1)'], 'a scrape returning nothing must not wipe what we already had'
    assert meta['Genre'] == [{'tag': 'Anal'}]


def test_a_scrape_that_found_something_replaces_the_stored_list() -> None:
    meta: dict[str, Any] = {'Genre': [{'tag': 'POV'}]}
    assert carry_emptied_fields(meta, _stored(Genre=[{'tag': 'Anal'}])) == []
    assert meta['Genre'] == [{'tag': 'POV'}]


def test_nothing_is_carried_when_there_is_no_snapshot() -> None:
    meta: dict[str, Any] = {'Genre': []}
    assert carry_emptied_fields(meta, None) == []
