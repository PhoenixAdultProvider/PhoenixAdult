from __future__ import annotations

import asyncio
from typing import Any

import pytest

from phoenixadult.clients.base import Client, SceneContext, SceneDetail
from phoenixadult.utils.http import rate_limit_helper
from phoenixadult.utils.http.rate_limit_helper import FastGate, PacingDeferredError


async def test_gate_runs_at_most_three_concurrently() -> None:
    gate = FastGate()
    running = 0
    peak = 0

    async def job() -> None:
        nonlocal running, peak
        async with gate.turn(True):
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.01)
            running -= 1

    await asyncio.gather(*(job() for _ in range(8)))
    assert peak == 3
    assert gate.state() == {'busy': 0, 'slots': 3, 'waiting': 0}


async def test_sync_turn_defers_when_slots_stay_full(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rate_limit_helper, '_SYNC_WAIT_BUDGET', 0.05)
    gate = FastGate()
    release = asyncio.Event()

    async def hold() -> None:
        async with gate.turn(True):
            await release.wait()

    holders = [asyncio.create_task(hold()) for _ in range(3)]
    await asyncio.sleep(0.01)
    assert gate.state()['busy'] == 3
    with pytest.raises(PacingDeferredError):
        async with gate.turn(False):
            pass
    release.set()
    await asyncio.gather(*holders)


async def test_slow_turn_waits_for_a_freed_slot() -> None:
    gate = FastGate(slots=1)
    order: list[str] = []

    async def first() -> None:
        async with gate.turn(True):
            order.append('first')
            await asyncio.sleep(0.02)

    async def second() -> None:
        await asyncio.sleep(0.005)
        async with gate.turn(True):
            order.append('second')

    await asyncio.gather(first(), second())
    assert order == ['first', 'second']


async def test_nested_turns_reuse_the_held_slot() -> None:
    gate = FastGate(slots=1)
    async with gate.turn(False), gate.turn(False):
        assert gate.state()['busy'] == 1
    assert gate.state()['busy'] == 0


class _StubClient(Client):
    async def _scene_detail_flow(self, payload: str, site: Any, ctx: SceneContext | None = None) -> SceneDetail | None:
        await asyncio.sleep(0.2)
        return SceneDetail(scene_url=payload)


async def test_unpaced_scene_detail_defers_through_the_shared_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rate_limit_helper, '_SYNC_WAIT_BUDGET', 0.05)
    monkeypatch.setattr('phoenixadult.clients.base.FAST_GATE', FastGate())
    client = _StubClient()
    site: Any = None

    inline = [asyncio.create_task(client.fetch_scene_detail(f'u{i}', site)) for i in range(3)]
    await asyncio.sleep(0.01)
    with pytest.raises(PacingDeferredError):
        await client.fetch_scene_detail('overflow', site)
    background = await client.fetch_scene_detail('slow-lane', site, SceneContext(allow_slow=True))
    assert background is not None and background.scene_url == 'slow-lane'
    assert [d.scene_url for d in await asyncio.gather(*inline) if d] == ['u0', 'u1', 'u2']
