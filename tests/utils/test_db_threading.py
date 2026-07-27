from __future__ import annotations

import threading
from typing import Any

import pytest

from phoenixadult.utils import db
from phoenixadult.utils.cache import scene_store

_THREADS = 4
_ROUNDS = 25


def _run(target: Any) -> list[Any]:
    out: list[Any] = []
    barrier = threading.Barrier(_THREADS)
    guard = threading.Lock()

    def worker() -> None:
        barrier.wait()
        result = target()
        with guard:
            out.append(result)

    threads = [threading.Thread(target=worker) for _ in range(_THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return out


def test_a_connection_is_never_shared_between_threads() -> None:
    assert len({id(conn) for conn in _run(db.connect)}) == _THREADS


def test_concurrent_readers_do_not_trip_over_each_other() -> None:
    site = 'Thicc18'
    for n in range(10):
        cur_id = f'c{n}'
        data = {
            'MediaContainer': {
                'identifier': 'p',
                'size': 1,
                'Metadata': [{'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': f'Scene {n}', 'studio': site, 'Genre': [{'tag': 'Gym'}]}],
            }
        }
        scene_store.upsert(site, cur_id, f'h{n}', f'archive/thicc18/{cur_id}', data)

    def hammer() -> int:
        return sum(1 for _ in range(_ROUNDS) for n in range(10) if scene_store.load(f'h{n}') is not None)

    assert _run(hammer) == [_ROUNDS * 10] * _THREADS


def test_a_stale_index_rebuilds_exactly_once_under_concurrent_readers() -> None:
    import time

    calls: list[int] = []

    def rebuild() -> None:
        calls.append(1)
        time.sleep(0.05)

    gate = db.ReconciledConn(lambda: 'some-cache-dir', rebuild)
    _run(gate.connect)

    assert len(calls) == 1


def test_a_failed_rebuild_is_retried_rather_than_marked_done() -> None:
    attempts: list[int] = []

    def rebuild() -> None:
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError('rebuild failed')

    gate = db.ReconciledConn(lambda: 'another-cache-dir', rebuild)
    with pytest.raises(RuntimeError):
        gate.connect()
    gate.connect()

    assert len(attempts) == 2


def test_a_reader_waits_for_an_in_flight_rebuild() -> None:
    import time

    state = {'building': False}
    started = threading.Event()

    def rebuild() -> None:
        state['building'] = True
        started.set()
        time.sleep(0.1)
        state['building'] = False

    gate = db.ReconciledConn(lambda: 'busy-cache-dir', rebuild)
    builder = threading.Thread(target=gate.connect)
    builder.start()
    started.wait(1)
    gate.connect()
    seen_mid_rebuild = state['building']
    builder.join()

    assert seen_mid_rebuild is False
