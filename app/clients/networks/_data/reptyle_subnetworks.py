from __future__ import annotations

import json
import re
from pathlib import Path

_SUBNETWORKS: dict[str, list[str]] = json.loads((Path(__file__).parent / 'json' / 'reptyle_subnetworks.json').read_text(encoding='utf-8'))


def _norm(s: str) -> str:
    return re.sub(r'\W', '', s).lower()


def resolve_reptyle_subnetwork(tagline: str) -> dict[str, str] | None:
    if not tagline:
        return None
    tagline_norm = _norm(tagline)
    for network, subsites in _SUBNETWORKS.items():
        for subsite in subsites:
            if _norm(subsite) == tagline_norm:
                return {'network': network, 'subsite': subsite}
    return None
