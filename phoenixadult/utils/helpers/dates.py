from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta


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
    if not raw:
        return None
    return raw[:10] if _ISO_PREFIX_RE.match(raw) else iso_date(raw)


def epoch_date(value: Any) -> str | None:
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
