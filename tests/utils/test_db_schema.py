def test_a_fresh_database_lands_on_the_latest_schema() -> None:
    from phoenixadult.utils import db

    conn = db.connect()
    assert conn.execute('PRAGMA user_version').fetchone()[0] == len(db._MIGRATIONS)
    tables = {r['name'] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {'scenes', 'users', 'sessions', 'client_hits', 'daily_requests', 'plex_connections'} <= tables


def test_a_pre_v1_database_is_refused_with_a_clear_error(tmp_path, monkeypatch) -> None:
    import sqlite3
    from contextlib import closing

    import pytest

    from phoenixadult.utils import db

    stale = tmp_path / 'old.db'
    with closing(sqlite3.connect(stale)) as raw:
        raw.execute('PRAGMA user_version = 16')
    monkeypatch.setenv('STATE_DB_PATH', str(stale))
    db.close()
    with pytest.raises(RuntimeError, match='does not know'):
        db.connect()
    db.close()


def test_the_connect_pass_renames_the_stored_day_theme_to_sky() -> None:
    from phoenixadult.utils import db
    from phoenixadult.utils.auth import user_store

    uid = user_store.create_user('themed', 'Hunter2hunter!', is_admin=True)
    conn = db.connect()
    with conn:
        conn.execute("UPDATE users SET theme_dark = 'midnight', theme_light = 'day' WHERE id = ?", (uid,))
    db.close()
    row = db.connect().execute('SELECT theme_dark, theme_light FROM users WHERE id = ?', (uid,)).fetchone()
    assert row['theme_light'] == 'sky', 'the idempotent connect pass rewrites stored day themes'
    assert row['theme_dark'] == 'midnight', 'other themes are untouched'


def test_a_v2_database_restamps_down_to_v1() -> None:
    from phoenixadult.utils import db

    conn = db.connect()
    with conn:
        conn.execute('PRAGMA user_version = 2')
    db.close()
    assert db.connect().execute('PRAGMA user_version').fetchone()[0] == 1, 'the folded v2 stamp collapses back to the baseline'
