from __future__ import annotations

import re

from app.registry import normalize_site_key
from app.utils.helpers.helpers import b64url_decode, b64url_encode


def to_rating_key(cur_id: str, site_name: str, date: str | None = None, subsite: str | None = None) -> str:
    cleaned = date.replace('-', '') if date else ''
    # Only an ISO date survives parse_rating_key's \d{8} round-trip.
    date_part = f'.{cleaned}' if len(cleaned) == 8 and cleaned.isdigit() else ''
    sub_part = f'~{b64url_encode(subsite)}' if subsite else ''
    return f'scene-{normalize_site_key(site_name)}-{cur_id}{date_part}{sub_part}'


def parse_rating_key(rating_key: str) -> dict[str, str | None] | None:
    m = re.match(r'^scene-([a-z0-9]+)-([A-Za-z0-9_-]+)(?:\.(\d{8}))?(?:~([A-Za-z0-9_-]+))?$', rating_key)
    if not m:
        return None
    date_raw = m.group(3)
    release_date = f'{date_raw[0:4]}-{date_raw[4:6]}-{date_raw[6:8]}' if date_raw else None
    subsite = b64url_decode(m.group(4)) if m.group(4) else None
    return {'site_name': m.group(1), 'cur_id': m.group(2), 'release_date': release_date, 'subsite': subsite}


def to_guid(rating_key: str, plex_identifier: str) -> str:
    return f'{plex_identifier}://movie/{rating_key}'
