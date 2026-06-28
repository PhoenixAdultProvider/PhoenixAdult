from __future__ import annotations

import base64
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta
from slugify import slugify as _slugify

from app.utils.logging.logger import logger
from app.utils.processors.similarity import compare_string

if TYPE_CHECKING:
    from app.clients.base import SearchResult


def load_site_json(caller_file: str, name: str) -> Any:
    """Load a per-site JSON fixture from the caller's sibling _data/json/<name>.json.
    Pass `__file__` as caller_file and the fixture's bare filename (no .json)."""
    return json.loads((Path(caller_file).parent / '_data' / 'json' / f'{name}.json').read_text(encoding='utf-8'))


# ── curID base64url codec (no padding, matching Node Buffer base64url) ────────


def b64url_encode(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode('utf-8')).rstrip(b'=').decode('ascii')


def b64url_decode(s: str) -> str:
    pad = '=' * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + pad).encode('ascii')).decode('utf-8')


def pack_cur_id(head: list[str]) -> str:
    return b64url_encode('|'.join(head))


def unpack_cur_id(encoded: str) -> dict[str, str | None]:
    raw = b64url_decode(encoded)
    pipe = raw.find('|')
    if pipe < 0:
        return {'head': raw, 'tail': None}
    tail = raw[pipe + 1 :].strip()
    return {'head': raw[:pipe], 'tail': tail or None}


# ── Slug ──────────────────────────────────────────────────────────────────────


def slugify(s: str) -> str:
    return _slugify(s)


# ── Dates ─────────────────────────────────────────────────────────────────────


def iso_date(raw: str, fmt: str | None = None, is_filename: bool = False) -> str | None:
    if not raw:
        return None
    trimmed = raw.strip()
    try:
        if fmt:
            d = datetime.strptime(trimmed, fmt)
        elif is_filename:
            m = re.match(r'^(\d{2}|\d{4})[.\s/-]+(\d{2})[.\s/-]+(\d{2})$', trimmed)
            if not m:
                return None
            year_fmt = '%y' if len(m.group(1)) == 2 else '%Y'
            d = datetime.strptime(f'{m.group(1)} {m.group(2)} {m.group(3)}', f'{year_fmt} %m %d')
        else:
            d = date_parser.parse(trimmed)
    except (ValueError, OverflowError):
        return None
    return f'{d.year:04d}-{d.month:02d}-{d.day:02d}'


_ISO_PREFIX_RE = re.compile(r'^\d{4}-\d{2}-\d{2}')


def api_date(raw: str | None) -> str | None:
    """An already-ISO date (YYYY-MM-DD…) is trimmed to its date prefix; anything else
    goes through iso_date. Common shape for JSON-API publishedAt/date fields."""
    if not raw:
        return None
    return raw[:10] if _ISO_PREFIX_RE.match(raw) else iso_date(raw)


def epoch_date(value: Any) -> str | None:
    """Unix timestamp (seconds, or milliseconds if > 1e11) → YYYY-MM-DD; None if unparsable."""
    try:
        ts = int(value)
    except (ValueError, TypeError):
        return None
    if ts > 1e11:  # milliseconds
        ts //= 1000
    return datetime.fromtimestamp(ts, tz=UTC).strftime('%Y-%m-%d')


_RELATIVE_AGO_RE = re.compile(r'(\d+|a|an)\s+(minute|hour|day|week|month|year)s?\s*ago\b')


def relative_iso_date(raw: str, now: datetime | None = None) -> str | None:
    if not raw:
        return None
    m = _RELATIVE_AGO_RE.search(raw.strip().lower())
    if not m:
        return None
    n = 1 if m.group(1) in ('a', 'an') else int(m.group(1))
    if n < 0:
        return None
    base = now if now is not None else datetime.now()
    unit = m.group(2)
    if unit == 'minute':
        d = base - timedelta(minutes=n)
    elif unit == 'hour':
        d = base - timedelta(hours=n)
    elif unit == 'day':
        d = base - timedelta(days=n)
    elif unit == 'week':
        d = base - timedelta(weeks=n)
    elif unit == 'month':
        d = base - relativedelta(months=n)
    else:
        d = base - relativedelta(years=n)
    return f'{d.year:04d}-{d.month:02d}-{d.day:02d}'


def format_duration(ms: int | None) -> str | None:
    if not ms:
        return None
    total_seconds = round(ms / 1000)
    hours = total_seconds // 3600
    minutes = (total_seconds - hours * 3600) // 60
    seconds = total_seconds - hours * 3600 - minutes * 60
    if hours > 0:
        return f'{hours:02d}:{minutes:02d}:{seconds:02d}'
    return f'{minutes}:{seconds:02d}'


# ── URLs ──────────────────────────────────────────────────────────────────────


def to_https(raw: str) -> str:
    """Upgrade a protocol-relative URL (//host/x) to https; pass anything else through."""
    return f'https:{raw}' if raw.startswith('//') else raw


def strip_query(url: str | None) -> str:
    """Drop the query string (everything from '?' on); '' for falsy input."""
    return (url or '').split('?')[0]


def join_url(path: str, base_url: str) -> str:
    """Prefix base_url when only a path is present; pass already-absolute (http) URLs
    through. Unlike absolute_url, a protocol-relative //host URL is kept relative to
    base (not upgraded to https)."""
    if path.startswith('http'):
        return path
    return f'{base_url}{path if path.startswith("/") else f"/{path}"}'


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


def apply_title_split(raw: str, split_on: str | None = None, index: int | None = None) -> str:
    if not raw or not split_on:
        return (raw or '').strip()
    parts = raw.split(split_on)
    idx = index if index is not None else 0
    try:
        return parts[idx].strip()
    except IndexError:
        return raw.strip()


# ── Scoring + search-result builder ───────────────────────────────────────────


def title_distance_score(query: str, title: str) -> int:
    return 80 - compare_string(query, title).levenshtein


def date_distance_score(search_date: str, release_date: str) -> int:
    return 80 - compare_string(search_date, release_date).levenshtein


def build_search_result(
    *,
    title: str,
    scene_url: str,
    query: str,
    search_date: str | None = None,
    display_date: str | None = None,
    score: float | None = None,
    cur_id: str | None = None,
    thumb_url: str | None = None,
    search_url: str | None = None,
) -> SearchResult:
    from app.clients.base import SearchResult  # local import to avoid a cycle

    if score is not None:
        computed = score
    elif search_date and display_date:
        computed = date_distance_score(search_date, display_date)
    else:
        computed = title_distance_score(query, title)

    logger.debug('Result Builder', f'Final score: {computed}')
    release_date = display_date or search_date or None
    if cur_id is None:
        cur_id = pack_cur_id([p for p in (scene_url, release_date) if p])

    return SearchResult(
        title=title,
        scene_url=scene_url,
        release_date=release_date,
        display_date=display_date or None,
        cur_id=cur_id,
        score=computed,
        thumb_url=thumb_url or None,
        search_url=search_url or None,
    )


def decensor(text: str, replacements: dict[str, str]) -> str:
    out = text
    for word, correction in replacements.items():
        if word in out:
            out = out.replace(word, correction)
    return out
