from __future__ import annotations

import asyncio

from phoenixadult.utils.concurrency.coalescer import Coalescer, coalesce_future


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
    await asyncio.sleep(0)
    gate.set()
    results = await asyncio.gather(*waiters)
    assert results == [42] * 5
    assert calls == 1


async def test_run_reexecutes_after_completion() -> None:
    c: Coalescer[str, int] = Coalescer()
    calls = 0

    async def factory() -> int:
        nonlocal calls
        calls += 1
        return calls

    assert await c.run('k', factory) == 1
    assert await c.run('k', factory) == 2


async def test_a_cancelled_first_caller_does_not_cancel_the_others() -> None:
    c: Coalescer[str, int] = Coalescer()
    gate = asyncio.Event()

    async def factory() -> int:
        await gate.wait()
        return 42

    leader = asyncio.create_task(c.run('k', factory))
    await asyncio.sleep(0)
    follower = asyncio.create_task(c.run('k', factory))
    await asyncio.sleep(0)
    leader.cancel()
    await asyncio.sleep(0)
    gate.set()
    assert await follower == 42
    assert leader.cancelled()


async def test_the_work_finishes_after_its_only_caller_leaves() -> None:
    c: Coalescer[str, int] = Coalescer()
    finished = asyncio.Event()

    async def factory() -> int:
        await asyncio.sleep(0.01)
        finished.set()
        return 1

    leader = asyncio.create_task(c.run('k', factory))
    await asyncio.sleep(0)
    leader.cancel()
    await asyncio.wait_for(finished.wait(), timeout=1)


async def test_coalesce_future_memoizes_for_dict_lifetime() -> None:
    cache: dict[str, asyncio.Future[int]] = {}
    calls = 0

    async def factory() -> int:
        nonlocal calls
        calls += 1
        return 7

    f1 = coalesce_future(cache, 'k', factory)
    f2 = coalesce_future(cache, 'k', factory)
    assert f1 is f2
    assert await f1 == 7
    assert await f2 == 7
    assert calls == 1


async def test_coalesce_future_distinct_keys() -> None:
    cache: dict[str, asyncio.Future[str]] = {}

    async def make(v: str) -> str:
        return v

    a = coalesce_future(cache, 'a', lambda: make('A'))
    b = coalesce_future(cache, 'b', lambda: make('B'))
    assert a is not b
    assert (await a, await b) == ('A', 'B')
