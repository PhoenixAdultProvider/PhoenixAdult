"""One-off purge: rewrite absolute people-image URLs in cached snapshots to host-relative.

Cached actor/director/producer photos (/images/local/...) used to be frozen with whatever
base built them (a tunnel FQDN, a LAN IP, …). They are now stored host-relative and the
PEOPLE_IMAGE_URL base is re-applied on every serve, but existing snapshots still hold the
old absolute URLs. This rewrites them in place so the on-disk data is reconfigurable too.

    python -m scripts.relativize_people_images
"""

from __future__ import annotations

import re
from pathlib import Path

from app.utils.cache import cache_dir

# http(s)://<host>/images/local/...  ->  /images/local/...   (people cache links only)
_ABS_LOCAL = re.compile(r'https?://[^/"\s]+(/images/local/[^"\s]*)')


def main() -> None:
    root = Path(cache_dir())
    scanned = changed = 0
    for meta in root.rglob('meta.json'):
        scanned += 1
        text = meta.read_text(encoding='utf-8')
        new = _ABS_LOCAL.sub(r'\1', text)
        if new != text:
            meta.write_text(new, encoding='utf-8')
            changed += 1
    print(f'relativized people image URLs in {changed}/{scanned} snapshot(s) under {root}')


if __name__ == '__main__':
    main()
