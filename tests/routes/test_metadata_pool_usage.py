from __future__ import annotations

from typing import Any

import pytest

from tests.conftest import authed_client


@pytest.fixture()
def store_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    import phoenixadult.routes.metadata_cache_routes as mcr

    seen: list[str] = []
    real = mcr.run_in

    async def counting(name: str, func: Any, /, *args: Any, **kwargs: Any) -> Any:
        seen.append(name)
        return await real(name, func, *args, **kwargs)

    monkeypatch.setattr(mcr, 'run_in', counting)
    return seen


def test_the_page_takes_one_store_worker_not_four(store_calls: list[str]) -> None:
    assert authed_client().get('/metadata').status_code == 200
    assert store_calls.count('store') == 1, f'one page load occupied {store_calls.count("store")} store workers'


def test_the_entries_api_takes_one_store_worker(store_calls: list[str]) -> None:
    assert authed_client().get('/metadata/entries').status_code == 200
    assert store_calls.count('store') == 1, f'one listing call occupied {store_calls.count("store")} store workers'


def test_the_duplicate_view_does_not_multiply_scans(store_calls: list[str]) -> None:
    assert authed_client().get('/metadata/entries?dups=2').status_code == 200
    assert store_calls.count('store') == 1
