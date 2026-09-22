from __future__ import annotations

import re

from phoenixadult.utils.helpers.data_files import load_data

_GUID = re.compile(r'^com\.plexapp\.agents\.phoenixadult://([^|]+)\|(\d+)(?:\||\?|$)')
_SITE_IDS: dict[str, str] = load_data(__file__, 'legacy_site_ids')


def payload(guid: str) -> str | None:
    match = _GUID.match(guid)
    return match.group(1) if match else None


def decode(guid: str) -> tuple[str, str] | None:
    match = _GUID.match(guid)
    if match is None:
        return None
    site_name = _SITE_IDS.get(match.group(2))
    return (site_name, match.group(1)) if site_name else None
