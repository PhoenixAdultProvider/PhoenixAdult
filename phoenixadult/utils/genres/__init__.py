from __future__ import annotations

import re
from dataclasses import dataclass, field

from phoenixadult.utils.genres.data import GenreRules, genre_rules
from phoenixadult.utils.processors.title_case import title_case


@dataclass(frozen=True)
class NormalizeGenresOptions:
    title: str | None = None
    site_name: str | None = None
    actors: tuple[str, ...] = field(default_factory=tuple)


def _match_key(value: str) -> str:
    return re.sub(r'\s+', ' ', value).strip().lower()


def normalize_genres(raws: list[str] | None, opts: NormalizeGenresOptions | None = None) -> list[str]:
    if not raws:
        return []
    opts = opts or NormalizeGenresOptions()
    rules = genre_rules()
    actor_keys = {key for key in (_match_key(name) for name in opts.actors) if key}
    seen: set[str] = set()
    out: list[str] = []
    for raw in raws:
        normalized = _normalize_one(raw, opts, rules, actor_keys)
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(normalized)
    return sorted(out, key=str.casefold)


def _normalize_one(raw: str | None, opts: NormalizeGenresOptions, rules: GenreRules, actor_keys: set[str]) -> str | None:
    if raw is None:
        return None

    cleaned = raw.replace('"', '').replace('\xa0', ' ').strip()
    if not cleaned:
        return None

    lower = cleaned.lower()

    if lower in rules.skip_set:
        return None

    for sub in rules.partial_skip:
        if sub in lower:
            return None

    canonical = rules.replace_lookup.get(lower)
    if canonical:
        return canonical

    if _match_key(cleaned) in actor_keys:
        return None

    cased = title_case(cleaned, site_name=opts.site_name, type='title')

    if len(cased) > 25:
        return None

    cased_lower = cased.lower()
    if opts.title:
        if cased_lower in opts.title.split(':')[0].lower():
            return None
        if cased_lower in opts.title.split('-')[0].lower():
            return None

    if len(cased.split()) > 4:
        return None

    return cased


__testing__ = {'genre_rules': genre_rules}
