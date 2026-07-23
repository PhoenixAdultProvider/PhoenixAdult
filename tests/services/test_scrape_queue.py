from __future__ import annotations

import asyncio

from app.services import scrape_queue


async def test_enqueue_runs_jobs_sequentially_and_dedupes() -> None:
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
    assert ran == ['a', 'b']
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


async def test_snapshot_reports_current_and_pending_by_kind() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow() -> None:
        started.set()
        await release.wait()

    async def noop() -> None:
        pass

    scrape_queue.enqueue('s1', slow, kind='search', label='Nubile Films — cool scene')
    scrape_queue.enqueue('u1', noop, kind='update', label='scene-abc')
    await asyncio.wait_for(started.wait(), timeout=5)

    snap = scrape_queue.snapshot()
    assert snap['pending'] == 2
    entries = snap['entries']
    assert isinstance(entries, list)
    assert entries[0]['key'] == 's1' and entries[0]['running'] is True and entries[0]['kind'] == 'search'
    assert entries[1]['key'] == 'u1' and entries[1]['running'] is False and entries[1]['kind'] == 'update'

    release.set()
    for _ in range(100):
        if scrape_queue.pending_count() == 0:
            break
        await asyncio.sleep(0.01)
    snap = scrape_queue.snapshot()
    assert snap['pending'] == 0 and snap['entries'] == [] and snap['paused'] is False


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
    from app.utils import db

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
