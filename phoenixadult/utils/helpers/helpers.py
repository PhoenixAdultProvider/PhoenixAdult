from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, overload
from urllib.parse import urljoin

from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta
from slugify import slugify as _slugify

from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.processors.similarity import compare_string
from phoenixadult.utils.processors.title_case import convert_sequence_numbers, title_case

if TYPE_CHECKING:
    from phoenixadult.clients.base import SearchResult


@overload
def load_data(caller_file: str, name: str, kind: Literal['json'] = 'json') -> Any: ...
@overload
def load_data(caller_file: str, name: str, kind: Literal['html']) -> str: ...
@overload
def load_data(caller_file: str, name: str, kind: Literal['path']) -> Path: ...
def load_data(caller_file: str, name: str, kind: Literal['json', 'html', 'path'] = 'json') -> Any:
    """Load a convention-placed asset relative to the caller's module (pass `__file__`): 'json'
    parses _data/json/<name>.json (bare name), 'html' reads html/<name>.html, 'path' -> _data/<name>."""
    folder = Path(caller_file).parent
    if kind == 'html':
        return (folder / 'html' / f'{name}.html').read_text(encoding='utf-8')
    if kind == 'path':
        return folder / '_data' / name
    return json.loads((folder / '_data' / 'json' / f'{name}.json').read_text(encoding='utf-8'))


# ── CurID Base64url Codec (no padding, matching Node Buffer base64url) ────────


def b64url_encode(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode('utf-8')).rstrip(b'=').decode('ascii')


def b64url_decode(s: str) -> str:
    pad = '=' * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + pad).encode('ascii')).decode('utf-8')


def pack_cur_id(head: list[str]) -> str:
    return b64url_encode('|'.join(head))


_SUBSITE_SEP = '\x1f'


def embed_subsite(cur_id: str, subsite: str | None) -> str:
    """Fold a sub-site into a (b64url) cur_id so it rides inside the opaque cur_id token
    and survives Plex's guid round-trip (a rating-key suffix does not). No-op when falsy."""
    if not subsite:
        return cur_id
    return b64url_encode(b64url_decode(cur_id) + _SUBSITE_SEP + subsite)


def split_subsite(decoded_cur_id: str) -> tuple[str, str | None]:
    """Inverse of embed_subsite on a decoded cur_id: (scraper payload, sub-site or None)."""
    payload, _, sub = decoded_cur_id.partition(_SUBSITE_SEP)
    return payload, sub or None


def unpack_cur_id(encoded: str) -> dict[str, str | None]:
    raw = b64url_decode(encoded)
    pipe = raw.find('|')
    if pipe < 0:
        return {'head': raw, 'tail': None}
    tail = raw[pipe + 1 :].strip()
    return {'head': raw[:pipe], 'tail': tail or None}


# ── Slug ──────────────────────────────────────────────────────────────────────


def slugify(s: str, **kwargs: Any) -> str:
    return _slugify(s, **kwargs)


def hash_key(*parts: str, sep: str, length: int | None = None) -> str:
    """Stable sha1 hex key of the sep-joined parts, truncated to `length` when given."""
    digest = hashlib.sha1(sep.join(parts).encode('utf-8')).hexdigest()  # noqa: S324 - non-crypto key
    return digest[:length] if length else digest


# ── Dates ─────────────────────────────────────────────────────────────────────


def iso_date(raw: str, fmt: str | None = None, is_filename: bool = False) -> str | None:
    if not raw:
        return None
    trimmed = raw.strip()
    try:
        if fmt:
            parsed = datetime.strptime(trimmed, fmt)
        elif is_filename:
            m = re.match(r'^(\d{2}|\d{4})[.\s/-]+(\d{2})[.\s/-]+(\d{2})$', trimmed)
            if not m:
                return None
            year_fmt = '%y' if len(m.group(1)) == 2 else '%Y'
            parsed = datetime.strptime(f'{m.group(1)} {m.group(2)} {m.group(3)}', f'{year_fmt} %m %d')
        else:
            parsed = date_parser.parse(trimmed)
    except (ValueError, OverflowError):
        return None
    return f'{parsed.year:04d}-{parsed.month:02d}-{parsed.day:02d}'


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
    if ts > 1e11:
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
    base = now if now is not None else datetime.now(UTC)
    unit = m.group(2)
    if unit == 'minute':
        shifted = base - timedelta(minutes=n)
    elif unit == 'hour':
        shifted = base - timedelta(hours=n)
    elif unit == 'day':
        shifted = base - timedelta(days=n)
    elif unit == 'week':
        shifted = base - timedelta(weeks=n)
    elif unit == 'month':
        shifted = base - relativedelta(months=n)
    else:
        shifted = base - relativedelta(years=n)
    return f'{shifted.year:04d}-{shifted.month:02d}-{shifted.day:02d}'


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
    """Prefix base_url when only a path is present; pass already-absolute (http) URLs through.
    Unlike absolute_url, a protocol-relative //host URL is kept relative to base."""
    if path.startswith('http'):
        return path
    return f'{base_url}{path if path.startswith("/") else f"/{path}"}'


def append_unique(items: list[str], raw: str | None, base_url: str | None = None) -> None:
    """Append a stripped URL to items unless empty or already present; resolve it
    against base_url when given."""
    value = (raw or '').strip()
    if not value:
        return
    if base_url:
        value = absolute_url(value, base_url)
    if value not in items:
        items.append(value)


def pad_jav_id(jav_id: str, ignore_labels: list[str]) -> str:
    """Zero-pad a JAVID's numeric part to 3 digits (ABC-1 -> ABC-001) unless the
    label is in ignore_labels."""
    label = jav_id.split('-')[0]
    num = '-'.join(jav_id.split('-')[1:])
    if len(num) >= 3 or any(item.lower() == label.lower() for item in ignore_labels):
        return jav_id
    return f'{label}-{num.zfill(3)}'


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


# ── Scoring + Search-Result Builder ───────────────────────────────────────────


def sceneid_distance_score(query: str, title: str) -> int:
    score = 100 - compare_string(query, title).levenshtein
    logger.debug('Scene ID Distance Score', f'Query: {query}, Title: {title}, Score: {score}')
    return score


_TITLE_CLEAN_RE = re.compile(r'[^a-z0-9]+', re.IGNORECASE)


def title_distance_score(query: str, title: str) -> int:
    def _score(q: str, t: str) -> int:
        return 100 - compare_string(_TITLE_CLEAN_RE.sub('', q).lower(), _TITLE_CLEAN_RE.sub('', t).lower()).levenshtein

    query, title = title_case(query), title_case(title)
    score = _score(query, title)
    nq, nt = convert_sequence_numbers(query), convert_sequence_numbers(title)
    if nq or nt:
        score = max(score, _score(nq or query, nt or title))
    logger.debug('Title Distance Score', f'Query: {query}, Title: {title}, Score: {score}')
    return score


def date_distance_score(search_date: str, release_date: str) -> int:
    score = 100 - compare_string(search_date, release_date).levenshtein
    logger.debug('Date Distance Score', f'Search Date: {search_date}, Release Date: {release_date}, Score: {score}')
    return score


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
    subsite: str | None = None,
) -> SearchResult:
    from phoenixadult.clients.base import SearchResult

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
        subsite=subsite or None,
    )


def decensor(text: str, replacements: dict[str, str]) -> str:
    out = text
    for word, correction in replacements.items():
        if word in out:
            out = out.replace(word, correction)
    return out
