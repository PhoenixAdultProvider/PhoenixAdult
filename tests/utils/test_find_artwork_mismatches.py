from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image as PILImage

from app.utils import db
from app.utils.cache import scene_store
from scripts.find_artwork_mismatches import scene_mismatches


def _seed(root: Path, rel: str, images: list[tuple[str, int, int, str]]) -> None:
    for name, width, height, _kind in images:
        target = root / rel / 'images' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        PILImage.new('RGB', (width, height)).save(target, format='JPEG')
    md = {
        'type': 'movie',
        'ratingKey': 'rk',
        'guid': 'g',
        'title': rel,
        'studio': 'Brazzers',
        'Image': [{'url': f'/cache/{rel}/images/{name}', 'type': kind} for name, _w, _h, kind in images],
    }
    scene_store.upsert('Brazzers', rel, rel, rel, {'MediaContainer': {'identifier': 'i', 'size': 1, 'Metadata': [md]}})


def test_flags_swapped_kinds_and_ignores_promoted_posters(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('STATE_DB_PATH', str(tmp_path / 'state.db'))
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    try:
        _seed(tmp_path, 'corrupt-scene', [('a.jpg', 400, 600, 'background'), ('b.jpg', 800, 450, 'coverPoster')])
        _seed(tmp_path, 'promoted-scene', [('c.jpg', 800, 450, 'coverPoster'), ('d.jpg', 800, 450, 'background')])
        _seed(tmp_path, 'gone-scene', [('e.jpg', 400, 600, 'coverPoster')])
        (tmp_path / 'gone-scene' / 'images' / 'e.jpg').unlink()

        flagged = {m['rel_path']: m['reasons'] for m in scene_mismatches()}
        assert 'portrait poster stored as background' in flagged['corrupt-scene']
        assert 'landscape image stored as coverPoster despite a real portrait poster' in flagged['corrupt-scene']
        assert 'missing or unreadable image file' in flagged['gone-scene']
        assert 'promoted-scene' not in flagged
    finally:
        db.close()
