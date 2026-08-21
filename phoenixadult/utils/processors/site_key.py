from __future__ import annotations

import re

from text_unidecode import unidecode


def normalize_site_key(token: str) -> str:
    return re.sub(r'[^a-z0-9]', '', unidecode(token).lower())
