from __future__ import annotations

import json
import re
from pathlib import Path

from app.utils.processors.title_case import title_case

_DATA = Path(__file__).parent / '_data' / 'json' / 'studios.json'
_raw = json.loads(_DATA.read_text(encoding='utf-8'))

CANONICAL_STUDIOS: list[str] = _raw['canonical']
STUDIO_ALIASES: dict[str, str] = _raw['aliases']


def _strip(s: str) -> str:
    return re.sub(r'\W', '', s).lower()


_CANONICAL_BY_STRIP = {_strip(s): s for s in CANONICAL_STUDIOS}
_ALIAS_BY_STRIP = {_strip(a): full for a, full in STUDIO_ALIASES.items()}


def normalize_studio(name: str, site_name: str = '') -> str:
    if not name:
        return ''

    from app.registry import canonical_site_display  # local import to avoid a cycle

    display = canonical_site_display(name)
    if display:
        return display

    n = _ALIAS_BY_STRIP.get(_strip(name), name)

    canonical = _CANONICAL_BY_STRIP.get(_strip(n))
    if canonical:
        return canonical

    return title_case(n, site_name=site_name)
