from __future__ import annotations

import re

from phoenixadult.models.metadata import PlexCollection, PlexGenre, PlexMetadata, PlexMetadataResponse, PlexRole
from phoenixadult.utils.genres import NormalizeGenresOptions, normalize_genres
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.people import apply_name_aliases
from phoenixadult.utils.processors.episode_tag import strip_episode_tag
from phoenixadult.utils.processors.studio_name import normalize_studio
from phoenixadult.utils.processors.text_normalize import normalize_text
from phoenixadult.utils.processors.title_case import title_case, title_sort

_EPISODE_TAGGED = {'nubiles', 'reptyle'}
_TITLE_HEADED_SUMMARY = {'scoregroup'}


def _recase_title(md: PlexMetadata, studio: str, scraper_type: str | None) -> bool:
    title = strip_episode_tag(md.title) if scraper_type in _EPISODE_TAGGED else md.title
    cased_title = title_case(title, site_name=studio, scraper_type=scraper_type)
    if not cased_title or cased_title == md.title:
        return False
    md.title = cased_title
    md.titleSort = title_sort(cased_title)
    return True


def _strip_title_heading(summary: str, title: str) -> str:
    for heading in (title, title.split(' - ')[0]):
        head = heading.strip()
        if not head or summary[: len(head)].casefold() != head.casefold():
            continue

        rest = summary[len(head) :].lstrip()
        if rest:
            return rest

    return summary


def _normalize_summary(md: PlexMetadata, scraper_type: str | None = None) -> bool:
    if not md.summary:
        return False
    cleaned_summary = normalize_text(md.summary)
    if scraper_type in _TITLE_HEADED_SUMMARY and md.title:
        cleaned_summary = _strip_title_heading(cleaned_summary, md.title)
    if cleaned_summary == md.summary:
        return False
    md.summary = cleaned_summary
    return True


def _recase_studio_tagline(md: PlexMetadata, studio: str) -> bool:
    changed = False
    cased_studio = normalize_studio(studio)
    if cased_studio and cased_studio != md.studio:
        md.studio = cased_studio
        changed = True
    if md.tagline:
        cased_tagline = normalize_studio(md.tagline)
        if cased_tagline != md.tagline:
            md.tagline = cased_tagline
            changed = True
    if md.tagline and md.tagline == md.studio:
        md.tagline = None
        changed = True
    return changed


def _recase_collections(md: PlexMetadata) -> bool:
    if not md.Collection:
        return False
    tags = list(dict.fromkeys(normalize_studio(c.tag) for c in md.Collection if c.tag))
    if tags == [c.tag for c in md.Collection]:
        return False
    md.Collection = [PlexCollection(tag=t) for t in tags]
    return True


def _renormalize_genres(md: PlexMetadata, studio: str) -> bool:
    if not md.Genre:
        return False
    old = [g.tag for g in md.Genre]
    actors = tuple(r.tag for r in md.Role or [] if r.tag)
    new = normalize_genres(old, NormalizeGenresOptions(title=md.title, site_name=studio, actors=actors))
    if new == old:
        return False
    md.Genre = [PlexGenre(tag=t) for t in new]
    return True


def _realias_people(md: PlexMetadata, studio: str) -> bool:
    changed = False
    for attr in ('Role', 'Director', 'Producer'):
        roles: list[PlexRole] | None = getattr(md, attr)
        if not roles:
            continue
        seen: set[str] = set()
        kept: list[PlexRole] = []
        for r in roles:
            cased_name = re.sub(r'\s+', ' ', title_case(r.tag, type='name', site_name=studio)).strip()
            aliased = apply_name_aliases(cased_name, studio, studio)
            if aliased != r.tag:
                logger.info('meta-cache', f'recredited "{r.tag}" as "{aliased}"')
                r.tag = aliased
                if r.thumb and '/images/local/' in r.thumb:
                    r.thumb = None
                changed = True
            if aliased.lower() in seen:
                changed = True
                continue
            seen.add(aliased.lower())
            kept.append(r)
        if len(kept) != len(roles):
            setattr(md, attr, kept)
    return changed


def reapply_text_rules(response: PlexMetadataResponse, scraper_type: str | None = None, locked: set[str] | None = None) -> bool:
    held = locked or set()
    changed = False
    for md in response.MediaContainer.Metadata:
        studio = md.studio or ''
        if 'title' not in held:
            changed = _recase_title(md, studio, scraper_type) or changed
        if 'summary' not in held:
            changed = _normalize_summary(md, scraper_type) or changed
        if not {'studio', 'tagline'} & held:
            changed = _recase_studio_tagline(md, studio) or changed
        if 'Collection' not in held:
            changed = _recase_collections(md) or changed
        if 'Genre' not in held:
            changed = _renormalize_genres(md, studio) or changed
        if not {'Role', 'Director', 'Producer'} & held:
            changed = _realias_people(md, studio) or changed
    return changed
