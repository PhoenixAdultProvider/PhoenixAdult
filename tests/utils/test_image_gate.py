from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_the_image_gate_is_shared_across_scene_writes() -> None:
    from phoenixadult.utils.cache import metadata as mc

    first = mc._image_gate()
    second = mc._image_gate()
    assert first is second, 'every scene write on one loop must share the same gate'
    assert first._value == mc.IMAGE_FETCH_CONCURRENCY
