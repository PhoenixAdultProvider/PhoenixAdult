from __future__ import annotations

import asyncio
import contextvars
import functools
import os
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal

PoolName = Literal['store', 'image', 'fs', 'auth', 'queue']

_CPU = os.cpu_count() or 4
_SIZES: dict[str, int] = {
    'store': max(8, min(32, _CPU + 4)),
    'image': max(2, min(8, _CPU // 2)),
    'fs': 4,
    'auth': 4,
    'queue': 1,
}

_pools: dict[str, ThreadPoolExecutor] = {}
_lock = threading.Lock()


def pool(name: PoolName) -> ThreadPoolExecutor:
    with _lock:
        if name not in _pools:
            _pools[name] = ThreadPoolExecutor(max_workers=_SIZES[name], thread_name_prefix=f'pa-{name}')
        return _pools[name]


async def run_in[T](name: PoolName, func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    loop = asyncio.get_running_loop()
    ctx = contextvars.copy_context()
    call = functools.partial(ctx.run, func, *args, **kwargs)
    return await loop.run_in_executor(pool(name), call)


def shutdown() -> None:
    with _lock:
        running = list(_pools.values())
        _pools.clear()
    for executor in running:
        executor.shutdown(wait=False, cancel_futures=True)


def sizes() -> dict[str, int]:
    return dict(_SIZES)
