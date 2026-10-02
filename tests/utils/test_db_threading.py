from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from phoenixadult.utils import db


@pytest.fixture()
def two_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[str, str]:
    first, second = str(tmp_path / 'first.db'), str(tmp_path / 'second.db')
    monkeypatch.setenv('STATE_DB_PATH', first)
    db.close()
    return first, second


def test_switching_databases_leaves_other_threads_connections_alive(two_paths: tuple[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    first, second = two_paths
    held: list[sqlite3.Connection] = []
    opened = threading.Event()
    release = threading.Event()
    failure: list[str] = []

    def worker() -> None:
        held.append(db.connect())
        opened.set()
        release.wait(timeout=10)
        try:
            held[0].execute('SELECT 1').fetchone()
        except sqlite3.ProgrammingError as err:
            failure.append(str(err))

    t = threading.Thread(target=worker)
    t.start()
    assert opened.wait(timeout=10)

    monkeypatch.setenv('STATE_DB_PATH', second)
    db.connect()

    release.set()
    t.join(timeout=10)
    assert not failure, f'a pool thread was left holding a closed connection: {failure[0]}'


def test_a_thread_reconnects_after_the_database_moves(two_paths: tuple[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    first, second = two_paths
    before = db.connect()
    monkeypatch.setenv('STATE_DB_PATH', second)
    after = db.connect()
    assert before is not after, 'a moved database must hand back a fresh connection'


def test_closing_from_the_owning_thread_still_closes(two_paths: tuple[str, str]) -> None:
    conn = db.connect()
    db.close()
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute('SELECT 1')


def _is_closed(conn: object) -> bool:
    import sqlite3

    try:
        conn.execute('SELECT 1')  # type: ignore[attr-defined]
    except sqlite3.ProgrammingError:
        return True
    return False


def test_a_finished_thread_closes_its_connection() -> None:
    import gc
    import threading

    from phoenixadult.utils import db

    opened: list[object] = []
    worker = threading.Thread(target=lambda: opened.append(db.connect()))
    worker.start()
    worker.join()
    gc.collect()
    assert opened and _is_closed(opened[0]), 'a dead thread must not leave its connection open'


def test_reconnecting_after_a_path_switch_closes_the_old_connection(tmp_path, monkeypatch) -> None:
    import shutil

    from phoenixadult.utils import db

    first = db.connect()
    moved = tmp_path / 'moved.db'
    shutil.copyfile(db.env.state_db_path, moved)
    monkeypatch.setenv('STATE_DB_PATH', str(moved))
    second = db.connect()
    assert second is not first and _is_closed(first)
