from __future__ import annotations

import asyncio
import re
from urllib.parse import quote

import httpx2

from app.models.metadata import PlexRole
from app.utils.logging.logger import logger
from app.utils.people.cache import cache_enabled, cache_photo, cache_replace_enabled, lookup_cached
from app.utils.people.data import ACTORS_REPLACE, ACTORS_REPLACE_STUDIOS, ACTORS_STUDIO_INDEXES
from app.utils.people.gender import gender_detect_enabled, iafd_gender_check
from app.utils.people.generic import gender_enabled, generic_image_enabled, generic_image_url
from app.utils.people.sources import find_photo
from app.utils.people.types import (
    Gender,
    PersonInput,
    PersonLookupContext,
    ResolvedPerson,
    Role,
)
from app.utils.processors.title_case import title_case

# fmt: off
_SKIP_NAMES = {'', 'Bad Name', 'Test Model Name'}
# fmt: on

_MAX_CONCURRENT_LOOKUPS = 3


def _clean_name(raw: str) -> str:
    return raw.replace('\xa0', ' ').replace(',', '').strip()


def _studio_index_for(studio: str, site_name: str) -> str | None:
    s1 = studio.lower()
    s2 = site_name.lower()
    for idx, names in ACTORS_STUDIO_INDEXES.items():
        lc = [n.lower() for n in names]
        if s1 in lc or s2 in lc:
            return idx
    return None


def _apply_alias_tables(name: str, studio: str, site_name: str) -> str:
    search = name.lower()
    idx = _studio_index_for(studio, site_name)
    if idx is not None and idx in ACTORS_REPLACE_STUDIOS:
        for canonical, aliases in ACTORS_REPLACE_STUDIOS[idx].items():
            if canonical.lower() == search or search in [a.lower() for a in aliases]:
                return canonical
    for canonical, aliases in ACTORS_REPLACE.items():
        if canonical.lower() == search or search in [a.lower() for a in aliases]:
            return canonical
    return name


async def _head_is_ok(url: str, headers: dict[str, str]) -> bool:
    try:
        async with httpx2.AsyncClient(timeout=8.0, verify=False, follow_redirects=True) as client:
            r = await client.head(url, headers=headers)
            return 200 <= r.status_code < 300
    except httpx2.HTTPError:
        return False


class _ResolveCtx:
    def __init__(self, studio: str, site_name: str, referers: list[str], cookies: list[str]) -> None:
        self.studio = studio
        self.site_name = site_name
        self.referers = referers
        self.cookies = cookies


def _image_headers(ctx: _ResolveCtx) -> dict[str, str]:
    headers: dict[str, str] = {}
    if ctx.referers:
        headers['Referer'] = ctx.referers[0]
    if ctx.cookies:
        headers['Cookie'] = '; '.join(ctx.cookies)
    return headers


class PeopleManager:
    def __init__(self) -> None:
        self._actors: list[PersonInput] = []
        self._directors: list[PersonInput] = []
        self._producers: list[PersonInput] = []
        self._sem = asyncio.Semaphore(_MAX_CONCURRENT_LOOKUPS)

    def add_actor(self, name: str, photo: str, gender: Gender = '') -> None:
        if any(a.name == name for a in self._actors):
            return
        self._actors.append(PersonInput(name=name, photo=photo, gender=gender))

    def add_director(self, name: str, photo: str) -> None:
        if any(a.name == name for a in self._directors):
            return
        self._directors.append(PersonInput(name=name, photo=photo))

    def add_producer(self, name: str, photo: str) -> None:
        if any(a.name == name for a in self._producers):
            return
        self._producers.append(PersonInput(name=name, photo=photo))

    async def resolve_all(
        self, *, studio: str, site_name: str, referers: list[str] | None = None, cookies: list[str] | None = None
    ) -> dict[str, list[ResolvedPerson]]:
        self._sem = asyncio.Semaphore(_MAX_CONCURRENT_LOOKUPS)
        ctx = _ResolveCtx(studio=studio, site_name=site_name, referers=referers or [], cookies=cookies or [])
        actors, directors, producers = await asyncio.gather(
            self._resolve_group(self._actors, 'actor', ctx),
            self._resolve_group(self._directors, 'director', ctx),
            self._resolve_group(self._producers, 'producer', ctx),
        )
        return {'actors': actors, 'directors': directors, 'producers': producers}

    async def _resolve_group(self, raw: list[PersonInput], role: Role, ctx: _ResolveCtx) -> list[ResolvedPerson]:
        nested = await asyncio.gather(*(self._resolve_entry(e, role, ctx) for e in raw))
        return [p for group in nested for p in group]

    async def _resolve_entry(self, entry: PersonInput, role: Role, ctx: _ResolveCtx) -> list[ResolvedPerson]:
        cleaned = _clean_name(entry.name)
        display = re.sub(r'\s+', ' ', title_case(cleaned, type='name', site_name=ctx.site_name)).strip()
        if display in _SKIP_NAMES:
            return []
        display = _apply_alias_tables(display, ctx.studio, ctx.site_name)

        if ',' in display:
            parts = [p.strip() for p in display.split(',') if p.strip()]
            nested = await asyncio.gather(*(self._resolve_entry(PersonInput(name=part, photo=entry.photo, gender=entry.gender), role, ctx) for part in parts))
            return [p for group in nested for p in group]

        async with self._sem:
            resolved = await self._resolve_photo(display, entry, role, ctx)

        if role == 'actor' and gender_enabled() and resolved.gender == 'male':
            logger.info('people', f'skipping male actor "{display}"')
            return []
        return [resolved]

    async def _detect_gender(self, name: str, role: Role, gender: Gender) -> Gender:
        if gender or role != 'actor' or not gender_detect_enabled():
            return gender
        return await iafd_gender_check(name) or gender

    async def _resolve_photo(self, name: str, entry: PersonInput, role: Role, ctx: _ResolveCtx) -> ResolvedPerson:
        lookup_ctx = PersonLookupContext(role=role, studio=ctx.studio, site_name=ctx.site_name)
        photo = ''
        gender: Gender = entry.gender or ''

        # 6a — local cache
        if cache_enabled() and not cache_replace_enabled():
            cached = lookup_cached(name, role)
            if cached:
                photo = cached['served_url']
                gender = gender or cached['gender']  # type: ignore[assignment]

        # 6b — scraped URL: HEAD-check then cache (use scene image Referer/Cookie).
        if not photo and entry.photo:
            headers = _image_headers(ctx)
            if await _head_is_ok(entry.photo, headers):
                gender = await self._detect_gender(name, role, gender)
                if cache_enabled():
                    cached = await cache_photo(entry.photo, name, role, gender, headers)
                    if cached:
                        photo = cached['served_url']
                        gender = gender or cached['gender']  # type: ignore[assignment]
                else:
                    photo = entry.photo

        # 6c — external sources
        if not photo:
            found = await find_photo(name, lookup_ctx)
            gender = gender or found.gender
            if found.url:
                gender = await self._detect_gender(name, role, gender)
                if cache_enabled():
                    cached = await cache_photo(found.url, name, role, gender)
                    photo = cached['served_url'] if cached else found.url
                else:
                    photo = found.url

        # 6d — generic fallback. Cache the silhouette under this person too, so the
        # next lookup is a local-cache hit instead of re-running the whole source chain.
        if not photo and generic_image_enabled() and gender in ('male', 'female'):
            generic_url = generic_image_url(gender)
            if cache_enabled():
                cached = await cache_photo(generic_url, name, role, gender)
                photo = cached['served_url'] if cached else generic_url
            else:
                photo = generic_url

        label = role.capitalize()
        if photo:
            logger.info(f'{label}: {name} {photo}')
            if gender:
                logger.info(f'Gender: {gender}')
        else:
            logger.info(f'{name} image not found')
        return ResolvedPerson(name=name, photo=photo, gender=gender, role=role)


# ── Convenience: resolved people → Plex Role[] ────────────────────────────────


def _proxy_photo(base_url: str, photo: str, referers: list[str], cookies: list[str]) -> str | None:
    if not photo:
        return None
    if photo.startswith(f'{base_url}/images/local/') or photo.startswith(f'{base_url}/images/proxy'):
        return photo
    out = f'{base_url}/images/proxy?url={quote(photo, safe="")}'
    for r in referers:
        out += f'&referer={quote(r, safe="")}'
    for c in cookies:
        out += f'&cookie={quote(c, safe="")}'
    return out


def to_plex_roles(people: list[ResolvedPerson], base_url: str, referers: list[str] | None = None, cookies: list[str] | None = None) -> list[PlexRole]:
    referers = referers or []
    cookies = cookies or []
    return [PlexRole(tag=p.name, thumb=_proxy_photo(base_url, p.photo, referers, cookies), gender=p.gender or None) for p in people]


__all__ = ['PeopleManager', 'to_plex_roles', 'find_photo', 'Gender', 'Role', 'PersonInput', 'ResolvedPerson']
