from __future__ import annotations

import asyncio

from phoenixadult.services import scrape_queue


async def test_enqueue_runs_every_job_once_and_dedupes() -> None:
    ran: list[str] = []
    done = asyncio.Event()

    def job(name: str, last: bool = False) -> object:
        async def _run() -> None:
            ran.append(name)
            if last:
                done.set()

        return _run

    assert scrape_queue.enqueue('a', job('a')) is True
    assert scrape_queue.enqueue('a', job('dup')) is False
    assert scrape_queue.enqueue('b', job('b', last=True)) is True
    assert scrape_queue.is_pending('a') is True
    await asyncio.wait_for(done.wait(), timeout=5)
    assert sorted(ran) == ['a', 'b']
    assert scrape_queue.pending_count() == 0
    assert scrape_queue.enqueue('a', job('a2', last=True)) is True


async def test_failed_job_never_kills_the_worker() -> None:
    done = asyncio.Event()

    async def boom() -> None:
        raise ValueError('boom')

    async def ok() -> None:
        done.set()

    scrape_queue.enqueue('bad', boom)
    scrape_queue.enqueue('good', ok)
    await asyncio.wait_for(done.wait(), timeout=5)
    assert scrape_queue.pending_count() == 0


async def _drain(timeout: float = 5.0) -> None:
    for _ in range(int(timeout * 100)):
        if scrape_queue.pending_count() == 0:
            return
        await asyncio.sleep(0.01)


async def test_snapshot_reports_running_before_pending() -> None:
    started = [asyncio.Event() for _ in range(4)]
    release = asyncio.Event()

    def slow(i: int):  # noqa: ANN202
        async def _run() -> None:
            started[i].set()
            await release.wait()

        return _run

    for i in range(4):
        scrape_queue.enqueue(f'j{i}', slow(i), kind='search', label=f'job {i}')
    await asyncio.wait_for(asyncio.gather(*(started[i].wait() for i in range(3))), timeout=5)

    snap = scrape_queue.snapshot()
    assert snap['pending'] == 4
    assert snap['running'] == 3
    entries = snap['entries']
    assert isinstance(entries, list)
    assert [e['running'] for e in entries] == [True, True, True, False]
    assert entries[3]['key'] == 'j3' and entries[3]['kind'] == 'search'
    assert not started[3].is_set()

    release.set()
    await _drain()
    snap = scrape_queue.snapshot()
    assert snap['pending'] == 0 and snap['entries'] == [] and snap['paused'] is False


async def test_the_fast_lane_runs_three_at_a_time() -> None:
    live = 0
    peak = 0
    release = asyncio.Event()

    async def job() -> None:
        nonlocal live, peak
        live += 1
        peak = max(peak, live)
        await release.wait()
        live -= 1

    for i in range(6):
        scrape_queue.enqueue(f'f{i}', job)
    await asyncio.sleep(0.05)
    assert peak == 3

    release.set()
    await _drain()
    assert peak == 3


async def test_the_paced_lane_runs_one_at_a_time() -> None:
    live = 0
    peak = 0
    seen = asyncio.Event()

    async def job() -> None:
        nonlocal live, peak
        live += 1
        peak = max(peak, live)
        seen.set()
        await asyncio.sleep(0.02)
        live -= 1

    for i in range(4):
        scrape_queue.enqueue(f'p{i}', job, paced=True)
    await asyncio.wait_for(seen.wait(), timeout=5)
    await _drain()
    assert peak == 1


async def test_a_paced_backlog_never_blocks_unpaced_jobs() -> None:
    release = asyncio.Event()
    fast_done = asyncio.Event()

    async def blocked() -> None:
        await release.wait()

    async def quick() -> None:
        fast_done.set()

    for i in range(3):
        scrape_queue.enqueue(f'slowpaced{i}', blocked, paced=True)
    scrape_queue.enqueue('unpaced', quick)

    await asyncio.wait_for(fast_done.wait(), timeout=5)
    assert scrape_queue.is_pending('slowpaced1') is True

    release.set()
    await _drain()


async def test_flush_drops_only_the_requested_kind() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow() -> None:
        started.set()
        await release.wait()

    async def noop() -> None:
        pass

    scrape_queue.enqueue('s-run', slow, kind='search')
    await asyncio.wait_for(started.wait(), timeout=5)
    scrape_queue.enqueue('s2', noop, kind='search')
    scrape_queue.enqueue('u2', noop, kind='update')
    assert scrape_queue.flush('search') == 1
    assert scrape_queue.is_pending('u2') is True
    assert scrape_queue.is_pending('s2') is False
    release.set()
    for _ in range(100):
        if scrape_queue.pending_count() == 0:
            break
        await asyncio.sleep(0.01)


async def test_pause_holds_the_worker_until_resume() -> None:
    ran = asyncio.Event()

    async def job() -> None:
        ran.set()

    scrape_queue.pause('test ban', 60.0)
    try:
        scrape_queue.enqueue('p1', job, kind='search')
        await asyncio.sleep(0.05)
        assert not ran.is_set()
        assert scrape_queue.snapshot()['paused'] is True
        scrape_queue.resume()
        await asyncio.wait_for(ran.wait(), timeout=5)
    finally:
        scrape_queue.resume()


async def test_replays_persist_and_drain_via_db(monkeypatch, tmp_path) -> None:
    from phoenixadult.utils import db

    monkeypatch.setenv('STATE_DB_PATH', str(tmp_path / 'state.db'))
    try:
        done = asyncio.Event()

        async def job() -> None:
            await done.wait()

        scrape_queue.enqueue('r1', job, kind='search', replay={'kind': 'search', 'provider': 'p'})
        assert scrape_queue.take_replays() == {'r1': {'kind': 'search', 'provider': 'p'}}
        assert scrape_queue.take_replays() == {}
        done.set()
    finally:
        db.close()


async def test_progress_counts_one_drain_cycle() -> None:
    release = asyncio.Event()

    async def job() -> None:
        await release.wait()

    for i in range(4):
        scrape_queue.enqueue(f'prog{i}', job)
    snap = scrape_queue.snapshot()
    assert snap['total'] == 4 and snap['done'] == 0

    release.set()
    await _drain()
    snap = scrape_queue.snapshot()
    assert snap['total'] == 0 and snap['done'] == 0


async def test_waiting_wakes_as_soon_as_a_job_finishes() -> None:
    release = asyncio.Event()

    async def job() -> None:
        await release.wait()

    scrape_queue.enqueue('watch1', job)
    await asyncio.sleep(0.02)
    before = int(scrape_queue.snapshot()['revision'])

    watcher = asyncio.create_task(scrape_queue.wait_for_change(before, 5.0))
    await asyncio.sleep(0.02)
    assert not watcher.done()

    release.set()
    await asyncio.wait_for(watcher, timeout=5)
    assert int(scrape_queue.snapshot()['revision']) > before
    await _drain()


async def test_waiting_returns_at_once_when_the_revision_already_moved() -> None:
    stale = int(scrape_queue.snapshot()['revision']) - 1
    await asyncio.wait_for(scrape_queue.wait_for_change(stale, 5.0), timeout=1)


async def test_waiting_gives_up_after_the_timeout() -> None:
    current = int(scrape_queue.snapshot()['revision'])
    await asyncio.wait_for(scrape_queue.wait_for_change(current, 0.05), timeout=2)
    assert int(scrape_queue.snapshot()['revision']) == current


async def test_progress_survives_a_partial_drain() -> None:
    release = asyncio.Event()
    started = asyncio.Event()

    async def quick() -> None:
        started.set()

    async def blocked() -> None:
        await release.wait()

    scrape_queue.enqueue('held', blocked)
    scrape_queue.enqueue('quick', quick)
    await asyncio.wait_for(started.wait(), timeout=5)

    snap = scrape_queue.snapshot()
    assert snap['total'] == 2 and snap['done'] == 1 and snap['pending'] == 1

    release.set()
    await _drain()
