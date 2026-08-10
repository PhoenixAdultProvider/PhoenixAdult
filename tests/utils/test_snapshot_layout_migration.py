from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from phoenixadult.utils import cache as mc
from phoenixadult.utils import db
from phoenixadult.utils.cache import scene_store
from phoenixadult.utils.cache.bundle_sweep import sweep
from scripts.migrate_snapshot_layout import migrate, orphans


@pytest.fixture(autouse=True)
def _tmp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    monkeypatch.setenv('STATE_DB_PATH', str(tmp_path / 'state.db'))
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path / 'cache'))
    yield tmp_path / 'cache'
    db.close()


def _response(title: str = 'A Scene') -> dict[str, object]:
    return {
        'MediaContainer': {
            'identifier': 'i',
            'size': 1,
            'Metadata': [
                {
                    'type': 'movie',
                    'ratingKey': 'rk',
                    'guid': 'g',
                    'title': title,
                    'studio': 'Old Studio',
                    'thumb': '/cache/oldnet/old-studio/h1abc/images/poster-00.jpg',
                    'Image': [{'url': '/cache/oldnet/old-studio/h1abc/images/poster-00.jpg', 'type': 'coverPoster'}],
                }
            ],
        }
    }


def _seed_legacy(root: Path, scene_hash: str = 'h1abc') -> str:
    rel = f'oldnet/old-studio/{scene_hash}'
    images = root / rel / 'images'
    images.mkdir(parents=True)
    (images / 'poster-00.jpg').write_bytes(b'JPEG')
    scene_store.upsert('Brazzers', 'cur-1', scene_hash, rel, _response(), {'/cache/oldnet/old-studio/h1abc/images/poster-00.jpg': (30, 45, 4)})
    return rel


def test_dry_run_reports_without_touching_anything(_tmp_db: Path) -> None:
    rel = _seed_legacy(_tmp_db)

    stats = migrate(_tmp_db, apply=False, prune=False)

    assert stats['moved'] == 1
    assert (_tmp_db / rel / 'images' / 'poster-00.jpg').exists()
    assert scene_store.legacy_count('scenes/%') == 1


def test_apply_moves_folders_rewrites_urls_and_writes_bundles(_tmp_db: Path) -> None:
    _seed_legacy(_tmp_db)
    new_rel = mc.bundle_path('h1abc')

    stats = migrate(_tmp_db, apply=True, prune=False)

    assert stats['moved'] == 1 and stats['bundled'] == 1
    assert (_tmp_db / new_rel / 'images' / 'poster-00.jpg').read_bytes() == b'JPEG'
    assert not (_tmp_db / 'oldnet').exists()
    assert scene_store.legacy_count('scenes/%') == 0

    conn = db.connect()
    assert conn.execute('SELECT rel_path FROM scenes').fetchone()['rel_path'] == new_rel
    assert conn.execute('SELECT thumb FROM scenes').fetchone()['thumb'] == f'/cache/{new_rel}/images/poster-00.jpg'
    assert conn.execute('SELECT rel_path FROM scene_images').fetchone()['rel_path'] == f'/cache/{new_rel}/images/poster-00.jpg'

    payload = json.loads((_tmp_db / new_rel / mc.BUNDLE_FILE).read_text(encoding='utf-8'))
    assert (payload['site'], payload['cur_id'], payload['hash']) == ('Brazzers', 'cur-1', 'h1abc')
    assert payload['images'][f'/cache/{new_rel}/images/poster-00.jpg'] == [30, 45, 4]


def test_apply_is_idempotent(_tmp_db: Path) -> None:
    _seed_legacy(_tmp_db)
    migrate(_tmp_db, apply=True, prune=False)

    stats = migrate(_tmp_db, apply=True, prune=False)

    assert stats['moved'] == 0 and stats['orphans'] == 0
    assert (_tmp_db / mc.bundle_path('h1abc') / 'images' / 'poster-00.jpg').exists()


def test_a_row_without_a_folder_still_gets_its_path_rewritten(_tmp_db: Path) -> None:
    rel = _seed_legacy(_tmp_db)
    import shutil

    shutil.rmtree(_tmp_db / rel)

    stats = migrate(_tmp_db, apply=True, prune=False)

    assert stats['rowonly'] == 1 and stats['moved'] == 0
    assert db.connect().execute('SELECT rel_path FROM scenes').fetchone()['rel_path'] == mc.bundle_path('h1abc')


def test_unreferenced_folders_are_reported_and_only_pruned_on_request(_tmp_db: Path) -> None:
    _seed_legacy(_tmp_db)
    stray = _tmp_db / 'ghost-studio' / 'deadbeef' / 'images'
    stray.mkdir(parents=True)
    (stray / 'poster-00.jpg').write_bytes(b'JPEG')
    staged = _tmp_db / '_plex-import' / 'abc' / 'images'
    staged.mkdir(parents=True)
    (staged / 'poster-00.jpg').write_bytes(b'JPEG')

    assert [p.name for p in orphans(_tmp_db)] == ['deadbeef']

    migrate(_tmp_db, apply=True, prune=False)
    assert (_tmp_db / 'ghost-studio' / 'deadbeef').exists()

    stats = migrate(_tmp_db, apply=True, prune=True)
    assert stats['orphans'] == 1
    assert not (_tmp_db / 'ghost-studio').exists()
    assert staged.exists()


def test_image_rows_whose_scene_is_gone_are_swept_with_the_orphans(_tmp_db: Path) -> None:
    _seed_legacy(_tmp_db)
    conn = db.connect()
    conn.execute('PRAGMA foreign_keys=OFF')
    with conn:
        conn.execute("INSERT INTO scene_images(scene_id, kind, rel_path, pos) VALUES(9999, 'coverPoster', '/cache/gone/x/images/p.jpg', 0)")
    conn.execute('PRAGMA foreign_keys=ON')

    assert migrate(_tmp_db, apply=True, prune=False)['stale_rows'] == 1
    assert scene_store.orphan_image_count() == 1

    assert migrate(_tmp_db, apply=True, prune=True)['stale_rows'] == 1
    assert scene_store.orphan_image_count() == 0
    assert db.connect().execute('SELECT COUNT(*) c FROM scene_images').fetchone()['c'] == 1


def test_bundles_rebuild_the_scene_rows_after_a_db_loss(_tmp_db: Path) -> None:
    _seed_legacy(_tmp_db)
    migrate(_tmp_db, apply=True, prune=False)
    new_rel = mc.bundle_path('h1abc')

    with db.connect() as conn:
        conn.execute('DELETE FROM scenes')
    assert scene_store.has('h1abc') is False

    stats = sweep(_tmp_db, overwrite=False)

    assert stats == {'adopted': 1, 'skipped': 0, 'unreadable': 0}
    assert scene_store.identity_for(new_rel) == ('Brazzers', 'cur-1')
    loaded = scene_store.load('h1abc')
    assert loaded is not None
    md = loaded['MediaContainer']['Metadata'][0]
    assert md['title'] == 'A Scene'
    assert md['Image'] == [{'url': f'/cache/{new_rel}/images/poster-00.jpg', 'type': 'coverPoster'}]


def test_rebuild_leaves_existing_rows_alone_unless_told_otherwise(_tmp_db: Path) -> None:
    _seed_legacy(_tmp_db)
    migrate(_tmp_db, apply=True, prune=False)

    assert sweep(_tmp_db, overwrite=False)['skipped'] == 1
    assert sweep(_tmp_db, overwrite=True)['adopted'] == 1


def test_a_corrupt_bundle_is_counted_and_skipped(_tmp_db: Path) -> None:
    _seed_legacy(_tmp_db)
    migrate(_tmp_db, apply=True, prune=False)
    (_tmp_db / mc.bundle_path('h1abc') / mc.BUNDLE_FILE).write_text('{not json', encoding='utf-8')

    stats = sweep(_tmp_db, overwrite=True)

    assert stats['unreadable'] == 1 and stats['adopted'] == 0
