from __future__ import annotations

import asyncio
import weakref

ARTWORK_PROBE = 16
DATA18_PROBE = 8
DATA18_GALLERY = 8
IMAGE_FETCH = 6
SCOREGROUP_SEARCH = 1

_gates: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, asyncio.Semaphore]] = weakref.WeakKeyDictionary()


def loop_gate(name: str, limit: int) -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    per_loop = _gates.get(loop)
    if per_loop is None:
        per_loop = {}
        _gates[loop] = per_loop
    gate = per_loop.get(name)
    if gate is None:
        gate = asyncio.Semaphore(limit)
        per_loop[name] = gate
    return gate


def limits() -> dict[str, int]:
    return {
        'artwork-probe': ARTWORK_PROBE,
        'data18-probe': DATA18_PROBE,
        'data18-gallery': DATA18_GALLERY,
        'image-fetch': IMAGE_FETCH,
        'scoregroup-search': SCOREGROUP_SEARCH,
    }
