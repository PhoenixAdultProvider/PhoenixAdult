from __future__ import annotations

from typing import Any

import pytest

from tests.conftest import authed_client


def test_bulk_refresh_looks_up_labels_once_not_once_per_scene(monkeypatch: pytest.MonkeyPatch) -> None:
    import phoenixadult.routes.metadata_cache_routes as mcr

    store_calls: list[str] = []
    real = mcr.run_in

    async def counting(name: str, func: Any, /, *args: Any, **kwargs: Any) -> Any:
        store_calls.append(name)
        return await real(name, func, *args, **kwargs)

    monkeypatch.setattr(mcr, 'run_in', counting)
    keys = [f'brazzers/scene-{n}' for n in range(25)]
    r = authed_client().post('/metadata/refresh-bulk', json={'keys': keys})
    assert r.status_code == 200, r.text
    assert store_calls.count('store') == 1, f'25 keys took {store_calls.count("store")} pooled round trips'


def test_the_label_helper_is_public_for_batching() -> None:
    from phoenixadult.services.metadata_service import queue_label

    assert queue_label('nonsense') == 'nonsense'
