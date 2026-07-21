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
