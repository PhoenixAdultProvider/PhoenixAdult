from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from app.config.env import env
from app.config.env_catalog import DEFAULT_SEARCH_TITLE_TRASH
from app.utils.helpers.helpers import iso_date
from app.utils.logging.logger import logger
from app.utils.processors.abbreviations import expand_abbreviations

SeparatorStyle = Literal['dot', 'space']


@dataclass(frozen=True)
class ParsedFilename:
    site_token: str
    date: str | None
    content: str | None
    content2: str | None
    style: SeparatorStyle


def is_digit(s: str) -> bool:
    return bool(re.match(r'^\d+$', s))


def _extract_leading_number(text: str) -> str | None:
    m = re.match(r'^(\d+)', text.strip())
    if not m:
        return None
    num = int(m.group(1))
    return str(num) if num > 100 else None


def _parse_space_date(tokens: list[str], offset: int) -> str | None:
    if len(tokens) < offset + 3:
        return None
    return iso_date(f'{tokens[offset]} {tokens[offset + 1]} {tokens[offset + 2]}', None, True)


def _strip_extension(filename: str) -> str:
    return re.sub(r'\.[a-z0-9]{2,5}$', '', filename, flags=re.IGNORECASE)


# ── Search-title cleanup ──────────────────────────────────────────────────────

_trash_source = ''
_trash_regex: re.Pattern[str] | None = None


def _trash_re() -> re.Pattern[str] | None:
    global _trash_source, _trash_regex
    extra = [s.strip() for s in (env.search_title_trash_raw or '').split(',') if s.strip()]
    tokens = list(dict.fromkeys([*DEFAULT_SEARCH_TITLE_TRASH, *extra]))
    source = '|'.join(tokens)
    if source != _trash_source:
        _trash_source = source
        _trash_regex = re.compile(rf'\b(?:{source})\b', re.IGNORECASE) if source else None
    return _trash_regex


def clean_search_title(title: str) -> str:
    re_ = _trash_re()
    stripped = re_.sub('', title) if re_ else title
    return re.sub(r'\s+', ' ', stripped).strip()


def apply_strip_symbols(title: str) -> str:
    if not env.strip_symbols_enabled:
        return title
    t = title
    sym = env.strip_symbol
    rev = env.strip_symbol_reverse
    if sym and sym in t:
        t = t.split(sym)[0]
    if rev and rev in t:
        t = t[t.rfind(rev) + len(rev) :]
    return t.strip()


def _parse(base: str, registry_lookup: Callable[[str], bool] | None = None) -> ParsedFilename | None:
    tokens = re.split(r'[.\s\-_,;:/]+', base)
    if not tokens:
        return None

    site_end_idx = 1
    if registry_lookup:
        for i in range(1, min(len(tokens), 4) + 1):
            candidate = ' '.join(tokens[:i])
            if registry_lookup(candidate):
                site_end_idx = i

    site_token = ' '.join(tokens[:site_end_idx])
    rest = tokens[site_end_idx:]

    date: str | None = None
    if rest:
        d1 = iso_date(rest[0], None, True)
        logger.debug('filenameParser', f'rest:{rest[0]} d1:{d1}')
        if d1:
            date = d1
            rest = rest[1:]
    if not date:
        d2 = _parse_space_date(rest, 0)
        logger.debug('filenameParser', f'rest:{rest} d2:{d2}')
        if d2:
            date = d2
            rest = rest[3:]

    rest_str = clean_search_title(' '.join(rest))
    content = _extract_leading_number(rest_str) or rest_str or None

    content2: str | None = None
    if content and is_digit(content):
        content2 = clean_search_title(' '.join(rest[1:])) or None

    return ParsedFilename(site_token=site_token, date=date, content=content, content2=content2, style='space')


def _manual_nfo_match(raw: str, registry_lookup: Callable[[str], bool]) -> ParsedFilename | None:
    token = env.manual_nfo_token
    if not token:
        return None
    prefix = f'{token}.'
    if raw.lower()[: len(prefix)] != prefix:
        return None
    basename = raw[len(prefix) :]
    if not basename:
        return None
    if not registry_lookup('Manual NFO'):
        return None
    return ParsedFilename(site_token='Manual NFO', date=None, content=basename, content2=None, style='dot')


def get_site_name_from_registry(filename: str, registry_lookup: Callable[[str], bool]) -> ParsedFilename | None:
    raw = _strip_extension(filename.split('\\')[-1]).strip()
    if not raw:
        return None

    manual = _manual_nfo_match(raw, registry_lookup)
    if manual:
        return manual

    base = expand_abbreviations(apply_strip_symbols(raw))
    parsed = _parse(base, registry_lookup)

    if not parsed or not parsed.site_token:
        return None
    if not registry_lookup(parsed.site_token):
        return None
    return parsed
