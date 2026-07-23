"""List scenes whose stored artwork kinds contradict the image files on disk, so only
those scenes need a forced refetch after the snapshot-rewrite scramble."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image as PILImage

from app.config.env import env
from app.utils import db
from app.utils.images.image_classifier import classify_image


def _file_class(path: Path) -> str | None:
    try:
        with PILImage.open(path) as im:
            width, height = im.size
    except (OSError, ValueError):
        return None
    return classify_image(width, height).image_class


def scene_mismatches() -> list[dict[str, str]]:
    """One entry per affected scene. A portrait poster stored as 'background' is always
    corruption (the classifier never emits that); a landscape 'coverPoster' is corruption
    only when the scene also holds a real portrait poster (otherwise it is a legitimate
    promoted fallback). Rows whose file is missing are reported too."""
    conn = db.connect()
    root = Path(env.metadata_cache_dir)
    rows = conn.execute(
        'SELECT s.rel_path scene_rel, s.title, s.site, si.kind, si.rel_path FROM scene_images si '
        "JOIN scenes s ON s.id = si.scene_id WHERE si.kind IN ('coverPoster', 'background') ORDER BY s.rel_path, si.pos"
    ).fetchall()

    by_scene: dict[str, dict[str, object]] = {}
    for row in rows:
        scene = by_scene.setdefault(str(row['scene_rel']), {'title': str(row['title']), 'site': str(row['site']), 'reasons': set()})
        reasons: set[str] = scene['reasons']  # type: ignore[assignment]
        target = root / str(row['rel_path']).removeprefix('/cache/')
        file_class = _file_class(target)
        if file_class is None:
            reasons.add('missing or unreadable image file')
        elif file_class == 'coverPoster':
            scene['has_portrait'] = True
            if row['kind'] == 'background':
                reasons.add('portrait poster stored as background')
        elif file_class == 'background' and row['kind'] == 'coverPoster':
            scene['landscape_poster'] = True

    out: list[dict[str, str]] = []
    for scene_rel, scene in sorted(by_scene.items()):
        reasons: set[str] = scene['reasons']  # type: ignore[assignment]
        if scene.get('landscape_poster') and scene.get('has_portrait'):
            reasons.add('landscape image stored as coverPoster despite a real portrait poster')
        if reasons:
            out.append({'rel_path': scene_rel, 'title': str(scene['title']), 'site': str(scene['site']), 'reasons': '; '.join(sorted(reasons))})
    return out


def main() -> int:
    mismatches = scene_mismatches()
    if not mismatches:
        print('No artwork mismatches found.')
        return 0
    print(f'{len(mismatches)} scene(s) need a forced refetch:\n')
    for m in mismatches:
        print(f'  {m["site"]} — {m["title"]}')
        print(f'    {m["rel_path"]}  ({m["reasons"]})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
