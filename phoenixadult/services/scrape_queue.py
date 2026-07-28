from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from phoenixadult.utils import db
from phoenixadult.utils.logging.logger import logger

_MAX_PENDING = 500


def _persist_add(key: str, replay: dict[str, Any]) -> None:
    conn = db.connect()
    conn.execute('INSERT OR REPLACE INTO queue_replays(key, replay, queued_at) VALUES(?, ?, ?)', (key, json.dumps(replay), time.time()))
    conn.commit()


def _persist_remove(key: str) -> None:
    conn = db.connect()
    conn.execute('DELETE FROM queue_replays WHERE key = ?', (key,))
    conn.commit()


def take_replays() -> dict[str, dict[str, Any]]:
    conn = db.connect()
    state = {str(r['key']): json.loads(r['replay']) for r in conn.execute('SELECT key, replay FROM queue_replays')}
    conn.execute('DELETE FROM queue_replays')
    conn.commit()
    return state


@dataclass
class QueueEntry:
    key: str
    kind: str
    label: str
    queued_at: float
    lane: str = 'fast'


FAST = 'fast'
PACED = 'paced'
_LANE_WORKERS = {FAST: 3, PACED: 1}

_queues: dict[str, asyncio.Queue[tuple[QueueEntry, Callable[[], Awaitable[object]]]]] = {}
_pending: dict[str, QueueEntry] = {}
_running: dict[str, float] = {}
_workers: dict[str, list[asyncio.Task[None]]] = {}
_loop_id: int | None = None
_cycle_total = 0
_cycle_done = 0
_paused_until: float = 0.0
_pause_reason: str = ''


def pause(reason: str, seconds: float) -> None:
    global _paused_until, _pause_reason
    _paused_until = time.monotonic() + seconds
    _pause_reason = reason
    logger.warn('scrape-queue', f'queue paused {seconds:.0f}s — {reason}')


def resume() -> None:
    global _paused_until, _pause_reason
    _paused_until = 0.0
    _pause_reason = ''
    logger.info('scrape-queue', 'queue resumed')


def paused_for() -> float:
    return max(0.0, _paused_until - time.monotonic())


def flush(kind: str) -> int:
    global _cycle_total, _cycle_done
    dropped = 0
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
        logger.info('scrape-queue', f'flushed {dropped} pending {kind} job(s)')
    return dropped


def _ensure_loop() -> None:
    global _queues, _pending, _running, _workers, _loop_id, _cycle_total, _cycle_done
    loop_id = id(asyncio.get_running_loop())
    if _loop_id != loop_id:
        _loop_id = loop_id
        _queues = {lane: asyncio.Queue() for lane in _LANE_WORKERS}
        _pending = {}
        _running = {}
        _workers = {lane: [] for lane in _LANE_WORKERS}
        _cycle_total = 0
        _cycle_done = 0


def _spawn_workers(lane: str) -> None:
    loop = asyncio.get_running_loop()
    alive = [task for task in _workers[lane] if not task.done()]
    want = min(_LANE_WORKERS[lane], _queues[lane].qsize())
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
        'pending': len(_pending),
        'running': len(_running),
        'slots': sum(_LANE_WORKERS.values()),
        'total': _cycle_total,
        'done': _cycle_done,
        'entries': rows,
        'paused': paused_for() > 0,
        'pauseReason': _pause_reason,
        'resumeIn': round(paused_for(), 1),
    }


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
            await asyncio.sleep(min(wait, 5.0))
        try:
            entry, job = queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        _running[entry.key] = time.monotonic()
        try:
            await job()
            logger.info('scrape-queue', f'background scrape finished {entry.key} ({len(_pending) - 1} pending)')
        except Exception as err:  # noqa: BLE001 - one failed job never kills the worker
            logger.warn('scrape-queue', f'background scrape failed {entry.key}: {err!r}')
        finally:
            _running.pop(entry.key, None)
            _pending.pop(entry.key, None)
            _persist_remove(entry.key)
            _mark_done()
