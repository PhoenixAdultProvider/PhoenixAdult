from __future__ import annotations

from phoenixadult.utils.concurrency import pools


def test_the_store_pool_can_outlast_one_page_load() -> None:
    assert pools.sizes()['store'] >= 8


def test_authentication_cannot_be_starved_by_reporting_queries() -> None:
    sizes = pools.sizes()
    assert 'auth' in sizes and sizes['auth'] >= 2
    assert pools.pool('auth') is not pools.pool('store')


def test_every_named_pool_is_reachable() -> None:
    for name in ('store', 'image', 'fs', 'auth'):
        assert pools.pool(name)._max_workers == pools.sizes()[name]
