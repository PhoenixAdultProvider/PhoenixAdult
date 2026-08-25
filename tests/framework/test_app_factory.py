from __future__ import annotations

import logging

import pytest

from phoenixadult.app_factory import _lifespan, create_app


async def test_lifespan_survives_a_failing_reconcile(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_the_image_gates_are_one_per_process_not_one_per_scene() -> None:
    import asyncio

    from phoenixadult.utils.concurrency.gate import loop_gate

    async def main() -> None:
        first = loop_gate('artwork-probe', 4)
        second = loop_gate('artwork-probe', 4)
        assert first is second, 'a per-call gate lets N concurrent scenes each open their own fan-out'
        assert loop_gate('data18-probe', 4) is not first

    asyncio.run(main())


def test_each_event_loop_gets_its_own_gates() -> None:
    import asyncio

    from phoenixadult.utils.concurrency.gate import loop_gate

    async def grab() -> object:
        return loop_gate('artwork-probe', 4)

    assert asyncio.run(grab()) is not asyncio.run(grab())


def test_the_banner_reports_the_limits_that_shape_bulk_throughput(caplog: pytest.LogCaptureFixture) -> None:
    from phoenixadult.app_factory import _log_startup_banner

    with caplog.at_level(logging.INFO):
        _log_startup_banner()
    printed = caplog.text
    for expected in ('Thread pools:', 'Queue lanes:', 'Fan-out caps:', 'artwork-probe=', 'store=', 'fast='):
        assert expected in printed, f'{expected!r} missing from the startup banner'
