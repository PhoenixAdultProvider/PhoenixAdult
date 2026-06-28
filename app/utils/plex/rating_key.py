from __future__ import annotations

import re


def to_rating_key(cur_id: str, site_name: str, date: str | None = None) -> str:
    normalized = re.sub(r'[^a-z0-9]', '', site_name.lower())
    date_part = f'.{date.replace("-", "")}' if date else ''
    return f'scene-{normalized}-{cur_id}{date_part}'


def parse_rating_key(rating_key: str) -> dict[str, str | None] | None:
    m = re.match(r'^scene-([a-z0-9]+)-([A-Za-z0-9_-]+)(?:\.(\d{8}))?$', rating_key)
    if not m:
        return None
    date_raw = m.group(3)
    release_date = f'{date_raw[0:4]}-{date_raw[4:6]}-{date_raw[6:8]}' if date_raw else None
    return {'site_name': m.group(1), 'cur_id': m.group(2), 'release_date': release_date}


def to_guid(rating_key: str, plex_identifier: str) -> str:
    return f'{plex_identifier}://movie/{rating_key}'
