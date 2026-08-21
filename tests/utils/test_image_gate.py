from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_the_image_gate_is_shared_across_scene_writes() -> None:
    """The cap must be global: per-scene semaphores meant N writes gave 6N concurrent fetches."""
    from phoenixadult.utils import cache as mc

    first = mc._image_gate()
    second = mc._image_gate()
    assert first is second, 'every scene write on one loop must share the same gate'
    assert first._value == mc.IMAGE_FETCH_CONCURRENCY
