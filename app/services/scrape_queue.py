from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config.env import env
from app.utils.logging.logger import logger

_MAX_PENDING = 500


def _state_path() -> Path:
    return Path(env.search_queue_dir) / 'queue-state.json'


def _read_state() -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(_state_path().read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_state(state: dict[str, dict[str, Any]]) -> None:
    try:
        _state_path().parent.mkdir(parents=True, exist_ok=True)
        _state_path().write_text(json.dumps(state), encoding='utf-8')
    except OSError as err:
        logger.warn('scrape-queue', f'could not persist queue state: {err}')


def _persist_add(key: str, replay: dict[str, Any]) -> None:
    state = _read_state()
    state[key] = replay
    _write_state(state)


def _persist_remove(key: str) -> None:
    state = _read_state()
    if state.pop(key, None) is not None:
        _write_state(state)


def take_replays() -> dict[str, dict[str, Any]]:
    """Drain persisted job descriptors (restart recovery); re-enqueueing re-persists them."""
    state = _read_state()
    if state:
        _write_state({})
    return state


@dataclass
class QueueEntry:
    key: str
    kind: str
    label: str
    queued_at: float


_queue: asyncio.Queue[tuple[QueueEntry, Callable[[], Awaitable[object]]]] | None = None
_pending: dict[str, QueueEntry] = {}
_current: QueueEntry | None = None
_current_started: float = 0.0
_worker: asyncio.Task[None] | None = None
_loop_id: int | None = None


def _ensure_loop() -> None:
    """Bind the queue/worker to the running loop; a new loop (tests) resets state."""
    global _queue, _pending, _current, _worker, _loop_id
    loop_id = id(asyncio.get_running_loop())
    if _loop_id != loop_id:
        _loop_id = loop_id
        _queue = asyncio.Queue()
        _pending = {}
        _current = None
        _worker = None


def enqueue(key: str, job: Callable[[], Awaitable[object]], *, kind: str = 'update', label: str = '', replay: dict[str, Any] | None = None) -> bool:
    """Queue a background job for the single sequential worker, deduped by key; False when
    already pending or full. `replay` persists a descriptor so the job survives a restart."""
    global _worker
    _ensure_loop()
    assert _queue is not None
    if key in _pending or len(_pending) >= _MAX_PENDING:
        return False
    entry = QueueEntry(key=key, kind=kind, label=label or key, queued_at=time.monotonic())
    _pending[key] = entry
    if replay is not None:
        _persist_add(key, replay)
    _queue.put_nowait((entry, job))
    if _worker is None or _worker.done():
        _worker = asyncio.get_running_loop().create_task(_run())
    logger.info('scrape-queue', f'queued background scrape {key} ({len(_pending)} pending)')
    return True


def is_pending(key: str) -> bool:
    return key in _pending


def pending_count() -> int:
    return len(_pending)


def snapshot() -> dict[str, object]:
    """Queue state for the /queue UI: the running entry plus pending entries in order."""
    try:
        _ensure_loop()
    except RuntimeError:
        pass
    now = time.monotonic()

    def row(entry: QueueEntry, *, running: bool) -> dict[str, object]:
        return {
            'key': entry.key,
            'kind': entry.kind,
            'label': entry.label,
            'waited': round(now - entry.queued_at, 1),
            'running': running,
            'running_for': round(now - _current_started, 1) if running else None,
        }

    rows = ([row(_current, running=True)] if _current is not None else []) + [
        row(e, running=False) for e in _pending.values() if _current is None or e.key != _current.key
    ]
    return {'pending': len(_pending), 'entries': rows}


async def _run() -> None:
    global _current, _current_started
    assert _queue is not None
    while True:
        try:
            entry, job = _queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        _current = entry
        _current_started = time.monotonic()
        try:
            await job()
            logger.info('scrape-queue', f'background scrape finished {entry.key} ({len(_pending) - 1} pending)')
        except Exception as err:  # noqa: BLE001 - one failed job never kills the worker
            logger.warn('scrape-queue', f'background scrape failed {entry.key}: {err!r}')
        finally:
            _current = None
            _pending.pop(entry.key, None)
            _persist_remove(entry.key)
