from __future__ import annotations

from dataclasses import dataclass

from app.utils.genres.data import PARTIAL_SKIP, REPLACE_LOOKUP, SKIP_SET
from app.utils.processors.title_case import title_case


@dataclass(frozen=True)
class NormalizeGenresOptions:
    title: str | None = None
    site_name: str | None = None


def normalize_genres(raws: list[str] | None, opts: NormalizeGenresOptions | None = None) -> list[str]:
    if not raws:
        return []
    opts = opts or NormalizeGenresOptions()
    seen: set[str] = set()
    out: list[str] = []
    for raw in raws:
        normalized = _normalize_one(raw, opts)
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(normalized)
    return out


def _normalize_one(raw: str | None, opts: NormalizeGenresOptions) -> str | None:
    if raw is None:
        return None

    # Step 1 — pre-clean: strip stray double quotes, NBSP → space, trim.
    cleaned = raw.replace('"', '').replace('\xa0', ' ').strip()
    if not cleaned:
        return None

    lower = cleaned.lower()

    # Step 2 — exact-match skip list.
    if lower in SKIP_SET:
        return None

    # Step 3 — substring partial-skip list.
    for sub in PARTIAL_SKIP:
        if sub in lower:
            return None

    # Step 4 — canonical alias replacement (canonical names are pre-typed).
    canonical = REPLACE_LOOKUP.get(lower)
    if canonical:
        return canonical

    # Step 5 — unknown → title-case it.
    cased = title_case(cleaned, site_name=opts.site_name, type='title')

    # Step 6 — heuristic skips (only for unknowns; mirrors `if not found and not skip`).
    if len(cased) > 25:
        return None

    cased_lower = cased.lower()
    if opts.title:
        if cased_lower in opts.title.split(':')[0].lower():
            return None
        if cased_lower in opts.title.split('-')[0].lower():
            return None

    # > 4 words is almost always a sentence fragment, not a tag.
    if len(cased.split()) > 4:
        return None

    return cased


__testing__ = {'REPLACE_LOOKUP': REPLACE_LOOKUP, 'SKIP_SET': SKIP_SET, 'PARTIAL_SKIP': PARTIAL_SKIP}
