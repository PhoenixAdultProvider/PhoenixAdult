from __future__ import annotations

import re

_EPISODE = r'S\d+\s*:?\s*E\d+'
_TRAILING_RE = re.compile(rf'\s*-\s*{_EPISODE}\s*$', re.IGNORECASE)
_LEADING_RE = re.compile(rf'^\s*{_EPISODE}\s*[:\-–]\s*', re.IGNORECASE)


def strip_episode_tag(title: str) -> str:
    if not title:
        return ''
    return _LEADING_RE.sub('', _TRAILING_RE.sub('', title)).strip()
