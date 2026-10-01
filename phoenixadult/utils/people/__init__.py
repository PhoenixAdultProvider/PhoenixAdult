from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx2

from phoenixadult.config.env import env
from phoenixadult.models.metadata import PlexMetadataResponse, PlexRole
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.http.client import shared_http
from phoenixadult.utils.http.headers import image_request_headers
from phoenixadult.utils.images.proxy import LOCAL_IMAGES, proxy_url
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.people.cache import cache_photo, lookup_cached
from phoenixadult.utils.people.data import actor_rules
from phoenixadult.utils.people.gender import iafd_gender_check
from phoenixadult.utils.people.generic import generic_image_url
from phoenixadult.utils.people.image_source import GENERIC_SOURCE, SCENE_SOURCE
from phoenixadult.utils.people.sources import find_photo, scene_image_pref
from phoenixadult.utils.people.types import (
    Gender,
    PersonInput,
    PersonLookupContext,
    PersonType,
    ResolvedPerson,
    parse_person_filename,
)
from phoenixadult.utils.processors.title_case import title_case

if TYPE_CHECKING:
    from phoenixadult.models.scrape import SceneDetail

# fmt: off
_SKIP_NAMES = {'', 'Bad Name', 'Test Model Name'}
# fmt: on

_MAX_CONCURRENT_LOOKUPS = 3


def _clean_name(raw: str) -> str:
    return raw.replace('\xa0', ' ').replace(',', '').strip()


def _studio_index_for(studio: str, site_name: str) -> str | None:
    lookup = actor_rules().studio_index_lookup
    hits = [hit for hit in (lookup.get(studio.replace(' ', '').lower()), lookup.get(site_name.replace(' ', '').lower())) if hit is not None]
    return min(hits)[1] if hits else None


def apply_name_aliases(name: str, studio: str, site_name: str) -> str:
    rules = actor_rules()
    search = name.lower()
    idx = _studio_index_for(studio, site_name)
    if idx is not None:
        canonical = rules.replace_studio_lookups.get(idx, {}).get(search)
        if canonical is not None:
            return canonical
    return rules.replace_lookup.get(search, name)


async def _head_is_ok(url: str, headers: dict[str, str]) -> bool:
    try:
        r = await shared_http('people-head', timeout=8.0).head(url, headers=headers)
        return 200 <= r.status_code < 300
    except httpx2.HTTPError:
        return False


@dataclass
class _ResolveCtx:
    studio: str
    site_name: str
    referers: list[str]
    cookies: list[str]


def _image_headers(ctx: _ResolveCtx) -> dict[str, str]:
    return image_request_headers(ctx.referers, ctx.cookies)


class PeopleResolver:
    def __init__(self) -> None:
        self._actors: list[PersonInput] = []
        self._directors: list[PersonInput] = []
        self._producers: list[PersonInput] = []
        self._seen: dict[str, set[str]] = {'actor': set(), 'director': set(), 'producer': set()}
        self._sem = asyncio.Semaphore(_MAX_CONCURRENT_LOOKUPS)

    def _add(self, kind: str, group: list[PersonInput], name: str, photo: str, gender: Gender = '', role: str = '') -> None:
        seen = self._seen[kind]
        if name in seen:
            return
        seen.add(name)
        group.append(PersonInput(name=name, photo=photo, gender=gender, role=role))

    def add_actor(self, name: str, photo: str, gender: Gender = '', role: str = '') -> None:
        self._add('actor', self._actors, name, photo, gender, role)

    def add_director(self, name: str, photo: str, role: str = '') -> None:
        self._add('director', self._directors, name, photo, role=role)

    def add_producer(self, name: str, photo: str, role: str = '') -> None:
        self._add('producer', self._producers, name, photo, role=role)

    def add_detail(self, detail: SceneDetail) -> None:
        for a in detail.actors or []:
            if a.name:
                self.add_actor(a.name, a.photo_url, a.gender or '', a.role)  # type: ignore[arg-type]
        for d in detail.directors or []:
            if d.name:
                self.add_director(d.name, d.photo_url, d.role)
        for pr in detail.producers or []:
            if pr.name:
                self.add_producer(pr.name, pr.photo_url, pr.role)

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

    async def _resolve_group(self, raw: list[PersonInput], type: PersonType, ctx: _ResolveCtx) -> list[ResolvedPerson]:
        nested = await asyncio.gather(*(self._resolve_entry(e, type, ctx) for e in raw))
        return [p for group in nested for p in group]

    async def _resolve_entry(self, entry: PersonInput, type: PersonType, ctx: _ResolveCtx) -> list[ResolvedPerson]:
        cleaned = _clean_name(entry.name)
        display = re.sub(r'\s+', ' ', title_case(cleaned, type='name', site_name=ctx.site_name)).strip()
        if display in _SKIP_NAMES:
            return []
        display = apply_name_aliases(display, ctx.studio, ctx.site_name)

        if ',' in display:
            parts = [p.strip() for p in display.split(',') if p.strip()]
            nested = await asyncio.gather(
                *(self._resolve_entry(PersonInput(name=part, photo=entry.photo, gender=entry.gender, role=entry.role), type, ctx) for part in parts)
            )
            return [p for group in nested for p in group]

        async with self._sem:
            resolved = await self._resolve_photo(display, entry, type, ctx)

        return [resolved]

    async def _detect_gender(self, name: str, type: PersonType, gender: Gender) -> Gender:
        if gender or type != 'actor' or not env.gender_detect_enabled:
            return gender
        return await iafd_gender_check(name) or gender

    async def _resolve_scene_photo(self, name: str, entry: PersonInput, type: PersonType, gender: Gender, ctx: _ResolveCtx) -> tuple[str, Gender]:
        if not entry.photo:
            return '', gender
        headers = _image_headers(ctx)
        if not await _head_is_ok(entry.photo, headers):
            return '', gender
        gender = await self._detect_gender(name, type, gender)
        if not env.people_cache_enabled:
            return entry.photo, gender
        cached = await cache_photo(entry.photo, name, type, gender, headers, source=SCENE_SOURCE)
        if cached:
            return cached['served_url'], gender or cached['gender']  # type: ignore[return-value]
        return '', gender

    async def _resolve_photo(self, name: str, entry: PersonInput, type: PersonType, ctx: _ResolveCtx) -> ResolvedPerson:
        lookup_ctx = PersonLookupContext(type=type, studio=ctx.studio, site_name=ctx.site_name)
        photo = ''
        gender: Gender = entry.gender or ''
        use_scene, scene_first = scene_image_pref()

        if env.people_cache_enabled and not env.people_cache_replace_enabled:
            cached = await run_in('store', lookup_cached, name, type)
            if cached:
                photo = cached['served_url']
                gender = gender or cached['gender']  # type: ignore[assignment]

        if not photo and use_scene and scene_first:
            photo, gender = await self._resolve_scene_photo(name, entry, type, gender, ctx)

        if not photo:
            found = await find_photo(name, lookup_ctx)
            gender = gender or found.gender
            if found.url:
                gender = await self._detect_gender(name, type, gender)
                if env.people_cache_enabled:
                    cached = await cache_photo(found.url, name, type, gender, source=found.source)
                    photo = cached['served_url'] if cached else found.url
                else:
                    photo = found.url

        if not photo and use_scene and not scene_first:
            photo, gender = await self._resolve_scene_photo(name, entry, type, gender, ctx)

        if not photo and env.generic_image_enabled and gender in ('male', 'female'):
            generic_url = generic_image_url(gender)
            if env.people_cache_enabled:
                cached = await cache_photo(generic_url, name, type, gender, source=GENERIC_SOURCE)
                photo = cached['served_url'] if cached else generic_url
            else:
                photo = generic_url

        label = type.capitalize()
        if photo:
            logger.info(f'{label}: {name} {photo}')
            if gender:
                logger.info(f'Gender: {gender}')
        else:
            logger.info(f'{name} image not found')
        return ResolvedPerson(name=name, photo=photo, role=entry.role, gender=gender, type=type)


# ── Convenience: resolved people → Plex Role[] ────────────────────────────────


def _proxy_photo(base_url: str, photo: str, referers: list[str], cookies: list[str]) -> str | None:
    return proxy_url(photo, base_url, referers, cookies, passthrough_local=True)


def to_plex_roles(people: list[ResolvedPerson], base_url: str, referers: list[str] | None = None, cookies: list[str] | None = None) -> list[PlexRole]:
    referers = referers or []
    cookies = cookies or []
    return [
        PlexRole(tag=p.name, role=p.role or None, thumb=_proxy_photo(base_url, p.photo, referers, cookies), gender=p.gender or None, order=idx)
        for idx, p in enumerate(people)
    ]


def _is_male_role(role: PlexRole) -> bool:
    gender = (role.gender or '').lower()
    if not gender and role.thumb and LOCAL_IMAGES in role.thumb:
        gender = parse_person_filename(role.thumb.rsplit('/', 1)[-1])[2]
    return gender == 'male'


def filter_male_actors(response: PlexMetadataResponse) -> int:
    if not env.gender_skip_male_enabled:
        return 0
    removed = 0
    for md in response.MediaContainer.Metadata:
        if not md.Role:
            continue
        kept = [r for r in md.Role if not _is_male_role(r)]
        removed += len(md.Role) - len(kept)
        md.Role = kept
    return removed


__all__ = ['PeopleResolver', 'to_plex_roles', 'filter_male_actors', 'apply_name_aliases', 'find_photo', 'Gender', 'PersonInput', 'ResolvedPerson']
