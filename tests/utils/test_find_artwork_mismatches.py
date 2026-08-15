from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image as PILImage

from phoenixadult.utils import db
from phoenixadult.utils.cache import scene_store
from scripts.find_artwork_mismatches import scene_mismatches


def _seed(root: Path, rel: str, images: list[tuple[str, int, int, str]], *, solid: bool = False) -> None:
    for name, width, height, _kind in images:
        if name.startswith('http'):
            continue
        target = root / rel / 'images' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        img = PILImage.new('RGB', (width, height)) if solid else PILImage.effect_noise((width, height), 90).convert('RGB')
        img.save(target, format='JPEG', quality=95)
    md = {
        'type': 'movie',
        'ratingKey': 'rk',
        'guid': 'g',
        'title': rel,
        'studio': 'Brazzers',
        'Image': [{'url': name if name.startswith('http') else f'/cache/{rel}/images/{name}', 'type': kind} for name, _w, _h, kind in images],
    }
    scene_store.upsert('Brazzers', rel, rel, rel, {'MediaContainer': {'identifier': 'i', 'size': 1, 'Metadata': [md]}})


def test_flags_swapped_kinds_and_ignores_promoted_and_upstream(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('STATE_DB_PATH', str(tmp_path / 'phoenixadult.db'))
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    try:
        _seed(tmp_path, 'corrupt-scene', [('a.jpg', 400, 600, 'background'), ('b.jpg', 800, 450, 'coverPoster')])
        _seed(tmp_path, 'promoted-scene', [('c.jpg', 800, 450, 'coverPoster'), ('d.jpg', 800, 450, 'background')])
        _seed(tmp_path, 'gone-scene', [('e.jpg', 400, 600, 'coverPoster')])
        (tmp_path / 'gone-scene' / 'images' / 'e.jpg').unlink()
        _seed(tmp_path, 'upstream-scene', [('https://cdn.example/p.jpg', 0, 0, 'coverPoster')])
        _seed(tmp_path, 'blank-scene', [('f.jpg', 400, 600, 'coverPoster')], solid=True)

        corrupted, unlocalized = scene_mismatches()
        flagged = {m['rel_path']: m['reasons'] for m in corrupted}
        assert 'portrait poster stored as background' in flagged['corrupt-scene']
        assert 'landscape image stored as coverPoster despite a real portrait poster' in flagged['corrupt-scene']
        assert 'dead local image link' in flagged['gone-scene']
        assert 'solid-color image (blank artwork)' in flagged['blank-scene']
        assert 'promoted-scene' not in flagged
        assert 'upstream-scene' not in flagged
        assert [m['rel_path'] for m in unlocalized] == ['upstream-scene']
    finally:
        db.close()
