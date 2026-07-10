from __future__ import annotations

import asyncio

from app.utils.concurrency.single_flight import SingleFlight


async def test_caches_until_expiry() -> None:
    sf: SingleFlight[str, str] = SingleFlight()
    calls = 0

    async def factory() -> tuple[str, float]:
        nonlocal calls
        calls += 1
        return f'v{calls}', 1e18

    assert await sf.get('k', factory) == 'v1'
    assert await sf.get('k', factory) == 'v1'
    assert calls == 1


async def test_expired_entry_refetches() -> None:
    sf: SingleFlight[str, str] = SingleFlight()
    calls = 0

    async def factory() -> tuple[str, float]:
        nonlocal calls
        calls += 1
        return f'v{calls}', 0.0

    assert await sf.get('k', factory) == 'v1'
    assert await sf.get('k', factory) == 'v2'
    assert calls == 2


async def test_concurrent_misses_coalesce() -> None:
    sf: SingleFlight[str, str] = SingleFlight()
    calls = 0
    gate = asyncio.Event()

    async def factory() -> tuple[str, float]:
        nonlocal calls
        calls += 1
        await gate.wait()
        return 'shared', 1e18

    waiters = [asyncio.create_task(sf.get('k', factory)) for _ in range(5)]
    await asyncio.sleep(0)
    gate.set()
    results = await asyncio.gather(*waiters)
    assert results == ['shared'] * 5
    assert calls == 1


async def test_factory_none_serves_stale_then_none() -> None:
    sf: SingleFlight[str, str] = SingleFlight()

    async def ok() -> tuple[str, float]:
        return 'cached', 0.0

    async def unavailable() -> tuple[str, float] | None:
        return None

    assert await sf.get('k', unavailable) is None
    assert await sf.get('k', ok) == 'cached'
    assert await sf.get('k', unavailable) == 'cached'


async def test_serve_stale_false_returns_none_on_failure() -> None:
    sf: SingleFlight[str, str] = SingleFlight(serve_stale=False)

    async def ok() -> tuple[str, float]:
        return 'cached', 0.0

    async def unavailable() -> tuple[str, float] | None:
        return None

    assert await sf.get('k', ok) == 'cached'
    assert await sf.get('k', unavailable) is None
