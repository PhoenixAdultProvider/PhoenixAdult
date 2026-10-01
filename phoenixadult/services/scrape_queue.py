from __future__ import annotations

import asyncio
import json
import math
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from phoenixadult.utils import db
from phoenixadult.utils.concurrency import pools
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.http import rate_limit_helper as pacing
from phoenixadult.utils.logging.logger import logger

_MAX_PENDING = 10_000


def _write_replay(key: str, replay: dict[str, Any]) -> None:
    conn = db.connect()
    conn.execute('INSERT OR REPLACE INTO queue_replays(key, replay, queued_at) VALUES(?, ?, ?)', (key, json.dumps(replay), time.time()))
    conn.commit()


def _delete_replay(key: str) -> None:
    conn = db.connect()
    conn.execute('DELETE FROM queue_replays WHERE key = ?', (key,))
    conn.commit()


def _report_persist_failure(future: asyncio.Future[None]) -> None:
    if not future.cancelled() and (err := future.exception()) is not None:
        logger.warn('scrape-queue', f'queue replay persistence failed: {err!r}')


def _persist(write: Callable[..., None], *args: Any) -> None:
    future = asyncio.get_running_loop().run_in_executor(pools.pool('queue'), write, *args)
    future.add_done_callback(_report_persist_failure)


def _persist_add(key: str, replay: dict[str, Any]) -> None:
    _persist(_write_replay, key, replay)


def _persist_remove(key: str) -> None:
    _persist(_delete_replay, key)


def _take_replays() -> dict[str, dict[str, Any]]:
    conn = db.connect()
    state = {str(r['key']): json.loads(r['replay']) for r in conn.execute('SELECT key, replay FROM queue_replays')}
    conn.execute('DELETE FROM queue_replays')
    conn.commit()
    return state


async def take_replays() -> dict[str, dict[str, Any]]:
    return await run_in('queue', _take_replays)


@dataclass
class QueueEntry:
    key: str
    kind: str
    label: str
    queued_at: float
    lane: str = 'fast'


FAST = 'fast'
PACED = 'paced'
_LANE_WORKERS = {FAST: 5, PACED: 1}


def lane_workers() -> dict[str, int]:
    return dict(_LANE_WORKERS)


_queues: dict[str, asyncio.Queue[tuple[QueueEntry, Callable[[], Awaitable[object]]]]] = {}
_pending: dict[str, QueueEntry] = {}
_running: dict[str, float] = {}
_workers: dict[str, list[asyncio.Task[None]]] = {}
_loop_id: int | None = None
_cycle_total = 0
_cycle_done = 0
_paused_until: float = 0.0
_pause_reason: str = ''
_revision = 0
_waiters: list[asyncio.Future[None]] = []
_durations: dict[str, deque[float]] = {FAST: deque(maxlen=20), PACED: deque(maxlen=20)}
_kind_paused: set[str] = set()
_held: dict[str, list[tuple[QueueEntry, Callable[[], Awaitable[object]]]]] = {FAST: [], PACED: []}
_DEFAULT_RUNTIME = 20.0


def _bump() -> None:
    global _revision
    _revision += 1
    if not _waiters:
        return
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    for waiter in _waiters:
        if not waiter.done():
            waiter.set_result(None)
    _waiters.clear()


def revision() -> int:
    return _revision


async def wait_for_change(since: int, timeout: float) -> None:
    try:
        _ensure_loop()
    except RuntimeError:
        return
    if since != _revision:
        return
    waiter: asyncio.Future[None] = asyncio.get_running_loop().create_future()
    _waiters.append(waiter)
    try:
        await asyncio.wait_for(waiter, timeout)
    except TimeoutError:
        pass
    finally:
        if waiter in _waiters:
            _waiters.remove(waiter)


def pause(reason: str, seconds: float) -> None:
    global _paused_until, _pause_reason
    _paused_until = time.monotonic() + seconds
    _pause_reason = reason
    _bump()
    logger.warn('scrape-queue', f'queue paused {seconds:.0f}s — {reason}')


def resume() -> None:
    global _paused_until, _pause_reason
    _paused_until = 0.0
    _pause_reason = ''
    _bump()
    logger.info('scrape-queue', 'queue resumed')


def pause_kind(kind: str) -> None:
    _kind_paused.add(kind)
    _bump()
    logger.info('scrape-queue', f'{kind} queue paused - queued {kind} jobs hold until resumed')


def resume_kind(kind: str) -> None:
    _kind_paused.discard(kind)
    for lane, queue in _queues.items():
        woken = [(e, j) for e, j in _held[lane] if e.kind == kind]
        if not woken:
            continue
        _held[lane] = [(e, j) for e, j in _held[lane] if e.kind != kind]
        drained: list[tuple[QueueEntry, Callable[[], Awaitable[object]]]] = []
        while True:
            try:
                drained.append(queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        for item in woken + drained:
            queue.put_nowait(item)
        _spawn_workers(lane)
    _bump()
    logger.info('scrape-queue', f'{kind} queue resumed')


def ban_cleared(reason: str) -> None:
    global _paused_until, _pause_reason
    if paused_for() > 0 and _pause_reason == reason:
        _paused_until = 0.0
        _pause_reason = ''
        logger.info('scrape-queue', 'queue resumed - the banned site is answering again')
    _bump()


def paused_for() -> float:
    return max(0.0, _paused_until - time.monotonic())


def remove(key: str) -> bool:
    global _cycle_total, _cycle_done
    if key not in _pending or key in _running:
        return False
    removed = False
    for lane, queue in _queues.items():
        kept: list[tuple[QueueEntry, Callable[[], Awaitable[object]]]] = []
        while True:
            try:
                entry, job = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if entry.key == key:
                removed = True
            else:
                kept.append((entry, job))
        for item in kept:
            queue.put_nowait(item)
        before = len(_held[lane])
        _held[lane] = [(e, j) for e, j in _held[lane] if e.key != key]
        removed = removed or len(_held[lane]) != before
    if not removed:
        return False
    _pending.pop(key, None)
    _persist_remove(key)
    _cycle_total = max(_cycle_done, _cycle_total - 1)
    if not _pending:
        _cycle_total = 0
        _cycle_done = 0
    _bump()
    logger.info('scrape-queue', f'removed queued job {key}')
    return True


def flush(kind: str) -> int:
    global _cycle_total, _cycle_done
    dropped = 0
    for lane in list(_held):
        for entry, _job in [(e, j) for e, j in _held[lane] if e.kind == kind]:
            _pending.pop(entry.key, None)
            _persist_remove(entry.key)
            dropped += 1
        _held[lane] = [(e, j) for e, j in _held[lane] if e.kind != kind]
    for queue in _queues.values():
        kept: list[tuple[QueueEntry, Callable[[], Awaitable[object]]]] = []
        while True:
            try:
                entry, job = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if entry.kind == kind:
                _pending.pop(entry.key, None)
                _persist_remove(entry.key)
                dropped += 1
            else:
                kept.append((entry, job))
        for item in kept:
            queue.put_nowait(item)
    if dropped:
        _cycle_total = max(_cycle_done, _cycle_total - dropped)
        if not _pending:
            _cycle_total = 0
            _cycle_done = 0
        _bump()
        logger.info('scrape-queue', f'flushed {dropped} pending {kind} job(s)')
    return dropped


def _ensure_loop() -> None:
    global _queues, _pending, _running, _workers, _loop_id, _cycle_total, _cycle_done, _waiters, _revision
    loop_id = id(asyncio.get_running_loop())
    if _loop_id != loop_id:
        _loop_id = loop_id
        _queues = {lane: asyncio.Queue() for lane in _LANE_WORKERS}
        _pending = {}
        _running = {}
        for lane in _held:
            _held[lane] = []
        _workers = {lane: [] for lane in _LANE_WORKERS}
        _cycle_total = 0
        _cycle_done = 0
        _waiters = []
        _revision += 1


def _spawn_workers(lane: str) -> None:
    loop = asyncio.get_running_loop()
    alive = [task for task in _workers[lane] if not task.done()]
    want = min(_LANE_WORKERS[lane], len(alive) + _queues[lane].qsize())
    while len(alive) < want:
        alive.append(loop.create_task(_run(lane)))
    _workers[lane] = alive


def enqueue(
    key: str,
    job: Callable[[], Awaitable[object]],
    *,
    kind: str = 'update',
    label: str = '',
    replay: dict[str, Any] | None = None,
    paced: bool = False,
) -> bool:
    global _cycle_total
    _ensure_loop()
    if key in _pending or len(_pending) >= _MAX_PENDING:
        return False
    _cycle_total += 1
    lane = PACED if paced else FAST
    entry = QueueEntry(key=key, kind=kind, label=label or key, queued_at=time.monotonic(), lane=lane)
    _pending[key] = entry
    if replay is not None:
        _persist_add(key, replay)
    _queues[lane].put_nowait((entry, job))
    _spawn_workers(lane)
    _bump()
    logger.info('scrape-queue', f'queued background scrape {key} on the {lane} lane ({len(_pending)} pending)')
    return True


def is_pending(key: str) -> bool:
    return key in _pending


def pending_count() -> int:
    return len(_pending)


def snapshot() -> dict[str, object]:
    try:
        _ensure_loop()
    except RuntimeError:
        pass
    now = time.monotonic()

    def row(entry: QueueEntry) -> dict[str, object]:
        started = _running.get(entry.key)
        return {
            'key': entry.key,
            'kind': entry.kind,
            'label': entry.label,
            'lane': entry.lane,
            'waited': round(now - entry.queued_at, 1),
            'running': started is not None,
            'running_for': round(now - started, 1) if started is not None else None,
        }

    rows = [row(e) for e in _pending.values() if e.key in _running] + [row(e) for e in _pending.values() if e.key not in _running]
    return {
        'etaSeconds': _estimate_eta(now),
        'pausedKinds': sorted(_kind_paused),
        'pending': len(_pending),
        'running': len(_running),
        'slots': sum(_LANE_WORKERS.values()),
        'total': _cycle_total,
        'done': _cycle_done,
        'entries': rows,
        'paused': paused_for() > 0,
        'pauseReason': _pause_reason,
        'resumeIn': round(paused_for(), 1),
        'revision': _revision,
    }


def _estimate_eta(now: float) -> int | None:
    if not _pending:
        return None

    def avg(lane: str) -> float:
        samples = _durations[lane]
        return sum(samples) / len(samples) if samples else _DEFAULT_RUNTIME

    def remaining(entry_key: str, lane: str) -> float:
        started = _running.get(entry_key)
        if started is None:
            return avg(lane)
        return max(0.0, avg(lane) - (now - started))

    runnable = [e for e in _pending.values() if e.kind not in _kind_paused or e.key in _running]
    fast = [e for e in runnable if e.lane == FAST]
    paced = [e for e in runnable if e.lane == PACED]
    eta_fast = math.ceil(len(fast) / _LANE_WORKERS[FAST]) * avg(FAST) if fast else 0.0
    per_paced_job = max(pacing.mean_scene_gap() + avg(PACED), pacing.scene_window_floor())
    pacer_wait = pacing.max_pending_wait() if paced else 0.0
    eta_paced = pacer_wait + sum(per_paced_job if e.key not in _running else remaining(e.key, PACED) for e in paced)
    return int(max(eta_fast, eta_paced) + paused_for())


def _mark_done() -> None:
    global _cycle_total, _cycle_done
    _cycle_done += 1
    if not _pending:
        _cycle_total = 0
        _cycle_done = 0


async def _run(lane: str) -> None:
    queue = _queues[lane]
    while True:
        while (wait := paused_for()) > 0:
            await wait_for_change(_revision, min(wait, 5.0))
        try:
            entry, job = queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        if entry.kind in _kind_paused:
            _held[lane].append((entry, job))
            continue
        _running[entry.key] = time.monotonic()
        _bump()
        try:
            await job()
            logger.info('scrape-queue', f'background scrape finished {entry.key} ({len(_pending) - 1} pending)')
        except Exception as err:  # noqa: BLE001 - one failed job never kills the worker
            logger.warn('scrape-queue', f'background scrape failed {entry.key}: {err!r}')
        finally:
            started = _running.pop(entry.key, None)
            if started is not None:
                _durations[lane].append(time.monotonic() - started)
            _pending.pop(entry.key, None)
            _persist_remove(entry.key)
            _mark_done()
            _bump()
