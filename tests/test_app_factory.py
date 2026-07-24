from __future__ import annotations

import pytest

from phoenixadult.app_factory import _lifespan, create_app


async def test_lifespan_survives_a_failing_reconcile(monkeypatch: pytest.MonkeyPatch) -> None:
    """A corrupt derived index (e.g. a bad state.db freelist) must degrade, not boot-loop the app."""
    from phoenixadult.routes import provider_router
    from phoenixadult.utils.images import logo_cache
    from phoenixadult.utils.people import cache as people_cache

    def _boom() -> None:
        raise RuntimeError('database disk image is malformed')

    async def _noop_restore() -> None:
        return None

    monkeypatch.setattr(logo_cache, 'reconcile', _boom)
    monkeypatch.setattr(people_cache, 'reconcile', _boom)
    monkeypatch.setattr(provider_router, 'restore_queue', _noop_restore)

    entered = False
    async with _lifespan(create_app()):
        entered = True
    assert entered
