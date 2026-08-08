def test_a_fresh_database_is_schema_v1() -> None:
    from phoenixadult.utils import db

    conn = db.connect()
    assert conn.execute('PRAGMA user_version').fetchone()[0] == 1
    tables = {r['name'] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {'scenes', 'users', 'sessions', 'client_hits', 'daily_requests', 'plex_connections'} <= tables


def test_a_pre_v1_database_is_refused_with_a_clear_error(tmp_path, monkeypatch) -> None:
    import sqlite3

    import pytest

    from phoenixadult.utils import db

    stale = tmp_path / 'old.db'
    with sqlite3.connect(stale) as raw:
        raw.execute('PRAGMA user_version = 16')
    monkeypatch.setenv('STATE_DB_PATH', str(stale))
    db.close()
    with pytest.raises(RuntimeError, match='predates schema v1'):
        db.connect()
    db.close()
