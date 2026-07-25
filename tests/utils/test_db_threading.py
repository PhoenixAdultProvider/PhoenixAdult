from __future__ import annotations

import threading
from typing import Any

from phoenixadult.utils import db
from phoenixadult.utils.cache import scene_store

_THREADS = 4
_ROUNDS = 25


def _run(target: Any) -> list[Any]:
    """Run target on _THREADS threads that are all alive at once, and collect what they return."""
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
