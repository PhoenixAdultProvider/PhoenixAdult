"""List scenes whose stored artwork kinds contradict the image files on disk, so only
those scenes need a forced refetch after the snapshot-rewrite scramble."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from phoenixadult.utils.cache import listing as cache_listing

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image as PILImage

from phoenixadult.config.env import env
from phoenixadult.utils import db
from phoenixadult.utils.images.image_classifier import classify_image
from phoenixadult.utils.images.image_fetcher import is_solid


def _inspect(path: Path) -> tuple[str, bool] | None:
    try:
        with PILImage.open(path) as im:
            width, height = im.size
            im.draft(None, (160, 160))
            solid = is_solid(im.convert('RGB') if im.mode == 'P' else im)
    except (OSError, ValueError):
        return None
    return classify_image(width, height).image_class, solid


def scene_mismatches() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """(corrupted, unlocalized) scene lists. Corruption = a portrait poster stored as
    'background' (the classifier never emits that), a landscape 'coverPoster' on a scene
    that also holds a real portrait poster, or a /cache/ row whose file is gone.
    Rows keeping upstream URLs are legitimate (image download failed at snapshot time)
    and only make the unlocalized list."""
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
        url = str(row['rel_path'])
        if not url.startswith('/cache/'):
            scene['unlocalized'] = True
            continue
        inspected = _inspect(root / url.removeprefix('/cache/'))
        if inspected is None:
            reasons.add('dead local image link (file missing or unreadable)')
            continue
        file_class, solid = inspected
        if solid:
            reasons.add('solid-color image (blank artwork)')
        if file_class == 'coverPoster':
            scene['has_portrait'] = True
            if row['kind'] == 'background':
                reasons.add('portrait poster stored as background')
        elif file_class == 'background' and row['kind'] == 'coverPoster':
            scene['landscape_poster'] = True

    corrupted: list[dict[str, str]] = []
    unlocalized: list[dict[str, str]] = []
    for scene_rel, scene in sorted(by_scene.items()):
        reasons: set[str] = scene['reasons']  # type: ignore[assignment]
        if scene.get('landscape_poster') and scene.get('has_portrait'):
            reasons.add('landscape image stored as coverPoster despite a real portrait poster')
        entry = {'rel_path': scene_rel, 'title': str(scene['title']), 'site': str(scene['site']), 'reasons': '; '.join(sorted(reasons))}
        if reasons:
            corrupted.append(entry)
        elif scene.get('unlocalized'):
            unlocalized.append(entry)
    return corrupted, unlocalized


def main() -> int:
    parser = argparse.ArgumentParser(description='Find scenes whose stored artwork kinds contradict the files on disk.')
    parser.add_argument('--show-unlocalized', action='store_true', help='also list scenes whose images still point upstream')
    parser.add_argument('--purge', action='store_true', help='delete the corrupted scenes (rows + folders) so a normal Plex refresh re-scrapes them')
    args = parser.parse_args()

    corrupted, unlocalized = scene_mismatches()
    if not corrupted:
        print('No artwork corruption found.')
    else:
        print(f'{len(corrupted)} scene(s) need a forced refetch:\n')
        for m in corrupted:
            print(f'  {m["site"]} — {m["title"]}')
            print(f'    {m["rel_path"]}  ({m["reasons"]})')
    if unlocalized:
        print(f'\n{len(unlocalized)} scene(s) serve upstream image URLs (download failed at snapshot time — optional refetch to localize):')
        if args.show_unlocalized:
            for m in unlocalized:
                print(f'  {m["site"]} — {m["title"]}  ({m["rel_path"]})')
    if args.purge and corrupted:
        removed = sum(1 for m in corrupted if cache_listing.purge(m['rel_path']))
        print(f'\nPurged {removed}/{len(corrupted)} scene(s); a normal Plex metadata refresh now re-scrapes them.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
