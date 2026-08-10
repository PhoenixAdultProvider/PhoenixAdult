from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from phoenixadult.utils.logging.logger import logger

KINDS = ('reconcile', 'import', 'collection-logos')
_RETAIN_SECONDS = 30 * 60

_jobs: dict[tuple[int, str], dict[str, Any]] = {}


def is_active(connection_id: int, kind: str) -> bool:
    return bool((_jobs.get((connection_id, kind)) or {}).get('active'))


def status_for(connection_id: int) -> dict[str, dict[str, Any]]:
    now = time.time()
    out: dict[str, dict[str, Any]] = {}
    for kind in KINDS:
        job = _jobs.get((connection_id, kind))
        if job is None:
            continue
        if not job['active'] and job.get('finishedAt') and now - job['finishedAt'] > _RETAIN_SECONDS:
            continue
        out[kind] = {k: v for k, v in job.items() if k != 'task'}
    return out


def launch(connection_id: int, kind: str, factory: Callable[[], Awaitable[Any]]) -> bool:
    if is_active(connection_id, kind):
        return False
    job: dict[str, Any] = {
        'active': True,
        'phase': 'starting',
        'total': 0,
        'done': 0,
        'report': None,
        'error': None,
        'startedAt': time.time(),
        'finishedAt': None,
    }
    _jobs[(connection_id, kind)] = job

    async def _run() -> None:
        try:
            report = await factory()
            job['report'] = report.as_dict() if hasattr(report, 'as_dict') else report
            job['phase'] = 'done'
        except Exception as err:  # noqa: BLE001 - a failed job reports its error, it never crashes the loop
            job['error'] = str(err) or err.__class__.__name__
            job['phase'] = 'error'
            logger.warn('plex-jobs', f'{kind} on connection {connection_id} failed: {err!r}')
        finally:
            job['active'] = False
            job['finishedAt'] = time.time()

    job['task'] = asyncio.create_task(_run())
    return True


def set_progress(connection_id: int, kind: str, *, total: int | None = None, done: int | None = None, phase: str | None = None) -> None:
    job = _jobs.get((connection_id, kind))
    if job is None:
        return
    if total is not None:
        job['total'] = total
    if done is not None:
        job['done'] = done
    if phase is not None:
        job['phase'] = phase


def reset() -> None:
    _jobs.clear()
