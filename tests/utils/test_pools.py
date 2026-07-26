from __future__ import annotations

import asyncio
import threading
import time

from phoenixadult.utils.concurrency import pools


async def test_each_pool_is_a_separate_bounded_executor() -> None:
    assert pools.pool('store') is not pools.pool('image')
    assert pools.pool('store') is pools.pool('store')
    assert pools.sizes()['store'] == 4


async def test_a_saturated_image_pool_does_not_delay_store_work() -> None:
    hold = threading.Event()
    try:
        blockers = [asyncio.create_task(pools.run_in('image', hold.wait, 5.0)) for _ in range(pools.sizes()['image'] + 4)]
        await asyncio.sleep(0.05)

        started = time.monotonic()
        assert await asyncio.wait_for(pools.run_in('store', lambda: 'served'), timeout=1.0) == 'served'
        assert time.monotonic() - started < 1.0
    finally:
        hold.set()
        await asyncio.gather(*blockers, return_exceptions=True)


async def test_run_in_propagates_the_return_value_and_exceptions() -> None:
    assert await pools.run_in('store', lambda a, b: a + b, 2, 3) == 5

    def boom() -> None:
        raise ValueError('nope')

    try:
        await pools.run_in('fs', boom)
    except ValueError as err:
        assert str(err) == 'nope'
    else:
        raise AssertionError('exception did not propagate')
