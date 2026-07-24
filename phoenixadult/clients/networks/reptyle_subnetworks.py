from __future__ import annotations

import re

from phoenixadult.utils.helpers.helpers import load_data

_SUBNETWORKS: dict[str, list[str]] = load_data(__file__, 'reptyle_subnetworks')


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
