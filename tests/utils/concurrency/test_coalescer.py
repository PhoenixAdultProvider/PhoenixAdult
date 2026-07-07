from __future__ import annotations

import asyncio

from app.utils.concurrency.coalescer import Coalescer, coalesce_future


async def test_run_coalesces_concurrent_calls() -> None:
    c: Coalescer[str, int] = Coalescer()
    calls = 0
    gate = asyncio.Event()

    async def factory() -> int:
        nonlocal calls
        calls += 1
        await gate.wait()
        return 42

    waiters = [asyncio.create_task(c.run('k', factory)) for _ in range(5)]
    await asyncio.sleep(0)  # let all five reach the coalescer
    gate.set()
    results = await asyncio.gather(*waiters)
    assert results == [42] * 5
    assert calls == 1  # one execution for five concurrent callers


async def test_run_reexecutes_after_completion() -> None:
    c: Coalescer[str, int] = Coalescer()
    calls = 0

    async def factory() -> int:
        nonlocal calls
        calls += 1
        return calls

    assert await c.run('k', factory) == 1
    assert await c.run('k', factory) == 2  # entry dropped after settling -> re-runs (no caching)


async def test_coalesce_future_memoizes_for_dict_lifetime() -> None:
    cache: dict[str, asyncio.Future[int]] = {}
    calls = 0

    async def factory() -> int:
        nonlocal calls
        calls += 1
        return 7

    f1 = coalesce_future(cache, 'k', factory)
    f2 = coalesce_future(cache, 'k', factory)
    assert f1 is f2  # same key -> same future
    assert await f1 == 7
    assert await f2 == 7  # result kept, not recomputed
    assert calls == 1


async def test_coalesce_future_distinct_keys() -> None:
    cache: dict[str, asyncio.Future[str]] = {}

    async def make(v: str) -> str:
        return v

    a = coalesce_future(cache, 'a', lambda: make('A'))
    b = coalesce_future(cache, 'b', lambda: make('B'))
    assert a is not b
    assert (await a, await b) == ('A', 'B')
