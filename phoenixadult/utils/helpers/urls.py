from __future__ import annotations

import re
from urllib.parse import urljoin

from w3lib.url import url_query_cleaner


def to_https(raw: str) -> str:
    return f'https:{raw}' if raw.startswith('//') else raw


def strip_query(url: str | None) -> str:
    return url_query_cleaner(url, []) if url else ''


def join_url(path: str, base_url: str) -> str:
    if path.startswith(('http://', 'https://')):
        return path
    return f'{base_url}{path if path.startswith("/") else f"/{path}"}'


def append_unique(items: list[str], raw: str | None, base_url: str | None = None) -> None:
    value = (raw or '').strip()
    if not value:
        return
    if base_url:
        value = absolute_url(value, base_url)
    if value not in items:
        items.append(value)


def absolute_url(u: str, base_url: str) -> str:
    if not u:
        return ''
    if u.startswith(('http://', 'https://')):
        return u
    if u.startswith('//'):
        return f'https:{u}'
    base = base_url if base_url.endswith('/') else f'{base_url}/'
    try:
        return urljoin(base, u)
    except ValueError:
        return u


def css_bg_image(style: str | None) -> str:
    if not style:
        return ''
    m = re.search(r"url\(\s*['\"]?\s*([^'\")\s]+)\s*['\"]?\s*\)", style, re.IGNORECASE)
    return m.group(1).strip() if m else ''
