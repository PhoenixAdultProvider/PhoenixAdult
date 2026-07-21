from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.utils.logging.logger import logger

if TYPE_CHECKING:
    from parsel import Selector

# ── Types ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Gallery:
    selector: str
    attr: str
    transform: Callable[[str, str], str] | None = None


@dataclass(frozen=True)
class FansiteAdapter:
    key: str
    display_name: str
    search_domain: str
    header_actor_selectors: tuple[str, ...]
    gallery: Gallery
    title_selector: str | None = None
    summary_selector: str | None = None
    uncategorized_fallback_selector: str | None = None


@dataclass(frozen=True)
class BadMatchOverride:
    site: str
    url: str
    actor_name: str | None = None


@dataclass
class FindFanArtOptions:
    sites: list[str]
    title: str
    actor_names: list[str]
    fetch_page: Callable[[str], Awaitable[Selector | None]]
    web_search: Callable[[str, str, int], Awaitable[list[str]]]


@dataclass
class FindFanArtResult:
    images: list[str] = field(default_factory=list)
    summary: str | None = None
    source: str | None = None


# ── Registries ─────────────────────────────────────────────────────────────────

_FANSITES: dict[str, FansiteAdapter] = {}
_NO_MATCH: set[str] = set()
_BAD_MATCH: dict[str, BadMatchOverride] = {}


def register_fansite(adapter: FansiteAdapter) -> None:
    _FANSITES[adapter.display_name.lower()] = adapter


def register_fanart_overrides(no_match: list[str] | None = None, bad_match: list[dict[str, str]] | None = None) -> None:
    for t in no_match or []:
        _NO_MATCH.add(_normalize_title(t))
    for entry in bad_match or []:
        _BAD_MATCH[_normalize_title(entry['title'])] = BadMatchOverride(site=entry['site'], url=entry['url'], actor_name=entry.get('actorName'))


# ── Title Normalization + Gates ───────────────────────────────────────────────


def _normalize_title(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[\s'’\\,]", '', s)
    return s.replace('&', 'and').strip()


def _titles_are_close_enough(scene_title: str, fan_title: str) -> bool:
    if not scene_title or not fan_title:
        return True
    a = scene_title.lower().strip()
    b = fan_title.lower().strip()
    if a in b:
        return True

    def tokenize(s: str) -> list[str]:
        return [t for t in re.sub(r"[’':,.]", '', s).split() if t]

    a_tokens = tokenize(a)
    b_set = set(tokenize(b))
    if not a_tokens:
        return True
    overlap = sum(1 for t in a_tokens if t in b_set) / len(a_tokens)
    return overlap >= 0.4


def _actor_matches_header(actor_names: list[str], header_names: list[str]) -> bool:
    if not header_names:
        return False
    haystacks = [h.lower() for h in header_names]
    for actor in actor_names:
        needle = actor.lower().strip()
        if not needle:
            continue
        if any(needle in h for h in haystacks):
            return True
    return False


def _extract_header_actors(node: Selector, adapter: FansiteAdapter) -> list[str]:
    for sel in adapter.header_actor_selectors:
        out = [t for el in node.xpath(sel) if (t := (el.xpath('normalize-space(.)').get() or '').strip())]
        if out:
            if adapter.uncategorized_fallback_selector and any(s == 'Uncategorized' for s in out):
                fb_nodes = node.xpath(adapter.uncategorized_fallback_selector)
                fallback = (fb_nodes[0].xpath('normalize-space(.)').get() or '').strip() if fb_nodes else ''
                if fallback:
                    out.append(fallback)
            return out
    return []


def _extract_title(node: Selector, adapter: FansiteAdapter, page_url: str) -> str:
    if not adapter.title_selector:
        return page_url.rstrip('/').split('/')[-1].replace('-', ' ')
    nodes = node.xpath(adapter.title_selector)
    return (nodes[0].xpath('normalize-space(.)').get() or '').strip() if nodes else ''


def _extract_gallery_images(node: Selector, adapter: FansiteAdapter, page_url: str) -> list[str]:
    out: list[str] = []
    for el in node.xpath(adapter.gallery.selector):
        raw = (el.attrib.get(adapter.gallery.attr) or '').strip()
        if not raw:
            continue
        transformed = adapter.gallery.transform(raw, page_url) if adapter.gallery.transform else raw
        if transformed and transformed not in out:
            out.append(transformed)
    return out


def _extract_summary(node: Selector, adapter: FansiteAdapter) -> str | None:
    if not adapter.summary_selector:
        return None
    nodes = node.xpath(adapter.summary_selector)
    text = (nodes[0].xpath('normalize-space(.)').get() or '').strip() if nodes else ''
    return text or None


# ── Lookups ────────────────────────────────────────────────────────────────────


def is_no_match_title(title: str) -> bool:
    return _normalize_title(title) in _NO_MATCH


def get_bad_match_override(title: str) -> BadMatchOverride | None:
    return _BAD_MATCH.get(_normalize_title(title))


def _get_adapter(display_name: str) -> FansiteAdapter | None:
    return _FANSITES.get(display_name.lower())


# ── Main Entry ─────────────────────────────────────────────────────────────────


async def find_fan_art(opts: FindFanArtOptions) -> FindFanArtResult:
    if is_no_match_title(opts.title):
        logger.debug('fanart', f'"{opts.title}" is in the no-match list — skipping')
        return FindFanArtResult()
    override = get_bad_match_override(opts.title)

    sites = [override.site] if override else opts.sites
    actor_names = [override.actor_name, *opts.actor_names] if override and override.actor_name else opts.actor_names
    query = f'{opts.actor_names[0] if opts.actor_names else ""} {opts.title}'.strip()

    for site_name in sites:
        adapter = _get_adapter(site_name)
        if not adapter:
            logger.warn('fanart', f'no adapter registered for "{site_name}"')
            continue

        if override:
            candidates = [override.url]
        else:
            try:
                candidates = await opts.web_search(query, adapter.search_domain, 2)
            except Exception as err:  # noqa: BLE001 - search failure is non-fatal
                logger.debug('fanart', f'webSearch {adapter.search_domain} failed: {err}')
                candidates = []

        for url in candidates:
            node = await opts.fetch_page(url)
            if not node:
                continue

            if not override:
                header_actors = _extract_header_actors(node, adapter)
                if not _actor_matches_header(actor_names, header_actors):
                    logger.debug('fanart', f'{site_name}: actor not in header ({", ".join(header_actors)})')
                    continue
                fan_title = _extract_title(node, adapter, url)
                if not _titles_are_close_enough(opts.title, fan_title):
                    logger.debug('fanart', f'{site_name}: title mismatch ("{fan_title}" vs "{opts.title}")')
                    continue

            images = _extract_gallery_images(node, adapter, url)
            if not images:
                logger.debug('fanart', f'{site_name}: matched but no gallery images extracted')
                continue

            logger.info('fanart', f'match on {site_name} ({len(images)} image(s)) for "{opts.title}"')
            return FindFanArtResult(images=images, summary=_extract_summary(node, adapter), source=site_name)

    return FindFanArtResult()


def _reset_overrides_for_tests() -> None:
    _NO_MATCH.clear()
    _BAD_MATCH.clear()


__testing__ = {'reset_overrides': _reset_overrides_for_tests, 'fansite_count': lambda: len(_FANSITES)}
