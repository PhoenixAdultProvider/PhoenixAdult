from __future__ import annotations

import asyncio
import re

import httpx2

from app.models.metadata import PlexMetadataResponse, PlexRole
from app.utils.http.client import make_http
from app.utils.http.headers import image_request_headers
from app.utils.images.proxy import proxy_url
from app.utils.logging.logger import logger
from app.utils.people.cache import cache_enabled, cache_photo, cache_replace_enabled, lookup_cached
from app.utils.people.data import actor_rules
from app.utils.people.gender import gender_detect_enabled, iafd_gender_check
from app.utils.people.generic import gender_skip_male_enabled, generic_image_enabled, generic_image_url
from app.utils.people.sources import find_photo, scene_image_pref
from app.utils.people.types import (
    Gender,
    PersonInput,
    PersonLookupContext,
    PersonType,
    ResolvedPerson,
    parse_person_filename,
)
from app.utils.processors.title_case import title_case

# fmt: off
_SKIP_NAMES = {'', 'Bad Name', 'Test Model Name'}
# fmt: on

_MAX_CONCURRENT_LOOKUPS = 3


def _clean_name(raw: str) -> str:
    return raw.replace('\xa0', ' ').replace(',', '').strip()


def _studio_index_for(studio: str, site_name: str) -> str | None:
    s1 = studio.replace(' ', '').lower()
    s2 = site_name.replace(' ', '').lower()
    for idx, names in actor_rules().studio_indexes.items():
        lc = [n.replace(' ', '').lower() for n in names]
        if s1 in lc or s2 in lc:
            return idx
    return None


def apply_name_aliases(name: str, studio: str, site_name: str) -> str:
    """Canonicalize a performer name through the actors.json alias tables (studio-specific
    first, then global). Used at resolve time and re-applied to cached scenes on serve."""
    rules = actor_rules()
    search = name.lower()
    idx = _studio_index_for(studio, site_name)
    if idx is not None and idx in rules.replace_studios:
        for canonical, aliases in rules.replace_studios[idx].items():
            if canonical.lower() == search or search in [a.lower() for a in aliases]:
                return canonical
    for canonical, aliases in rules.replace.items():
        if canonical.lower() == search or search in [a.lower() for a in aliases]:
            return canonical
    return name


async def _head_is_ok(url: str, headers: dict[str, str]) -> bool:
    try:
        async with make_http(timeout=8.0) as client:
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
    return image_request_headers(ctx.referers, ctx.cookies)


class PeopleManager:
    def __init__(self) -> None:
        self._actors: list[PersonInput] = []
        self._directors: list[PersonInput] = []
        self._producers: list[PersonInput] = []
        self._sem = asyncio.Semaphore(_MAX_CONCURRENT_LOOKUPS)

    def add_actor(self, name: str, photo: str, gender: Gender = '', role: str = '') -> None:
        if any(a.name == name for a in self._actors):
            return
        self._actors.append(PersonInput(name=name, photo=photo, gender=gender, role=role))

    def add_director(self, name: str, photo: str, role: str = '') -> None:
        if any(a.name == name for a in self._directors):
            return
        self._directors.append(PersonInput(name=name, photo=photo, role=role))

    def add_producer(self, name: str, photo: str, role: str = '') -> None:
        if any(a.name == name for a in self._producers):
            return
        self._producers.append(PersonInput(name=name, photo=photo, role=role))

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

        # Male actors are always resolved + cached (caching their image/gender speeds up
        # future scenes); the male-actor filter is applied at serve time, not here, so it
        # also covers already-cached snapshots. See filter_male_actors.
        return [resolved]

    async def _detect_gender(self, name: str, type: PersonType, gender: Gender) -> Gender:
        if gender or type != 'actor' or not gender_detect_enabled():
            return gender
        return await iafd_gender_check(name) or gender

    async def _resolve_scene_photo(self, name: str, entry: PersonInput, type: PersonType, gender: Gender, ctx: _ResolveCtx) -> tuple[str, Gender]:
        """The actor image from the scene page (entry.photo), HEAD-checked and cached with the
        scene's Referer/Cookie. Returns (photo, gender); ('', gender) when there's nothing usable."""
        if not entry.photo:
            return '', gender
        headers = _image_headers(ctx)
        if not await _head_is_ok(entry.photo, headers):
            return '', gender
        gender = await self._detect_gender(name, type, gender)
        if not cache_enabled():
            return entry.photo, gender
        cached = await cache_photo(entry.photo, name, type, gender, headers)
        if cached:
            return cached['served_url'], gender or cached['gender']  # type: ignore[return-value]
        return '', gender

    async def _resolve_photo(self, name: str, entry: PersonInput, type: PersonType, ctx: _ResolveCtx) -> ResolvedPerson:
        lookup_ctx = PersonLookupContext(type=type, studio=ctx.studio, site_name=ctx.site_name)
        photo = ''
        gender: Gender = entry.gender or ''
        use_scene, scene_first = scene_image_pref()

        if cache_enabled() and not cache_replace_enabled():
            cached = lookup_cached(name, type)
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
                if cache_enabled():
                    cached = await cache_photo(found.url, name, type, gender, source=found.source)
                    photo = cached['served_url'] if cached else found.url
                else:
                    photo = found.url

        if not photo and use_scene and not scene_first:
            photo, gender = await self._resolve_scene_photo(name, entry, type, gender, ctx)

        # 6d — generic fallback. Cache the silhouette under this person too, so the
        # next lookup is a local-cache hit instead of re-running the whole source chain.
        if not photo and generic_image_enabled() and gender in ('male', 'female'):
            generic_url = generic_image_url(gender)
            if cache_enabled():
                cached = await cache_photo(generic_url, name, type, gender)
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
    if not gender and role.thumb and '/images/local/' in role.thumb:
        gender = parse_person_filename(role.thumb.rsplit('/', 1)[-1])[2]  # gender lives in the cache filename
    return gender == 'male'


def filter_male_actors(response: PlexMetadataResponse) -> int:
    """Drop male actors from the served Role list when the male-actor filter (GENDER_SKIP_MALE_ENABLE)
    is on. The only place male actors are hidden: they're always resolved and cached (faster
    future gender resolution) and filtered out only when serving. Non-destructive — mutates
    the in-memory response only, so snapshots keep every actor on disk. Returns count removed."""
    if not gender_skip_male_enabled():
        return 0
    removed = 0
    for md in response.MediaContainer.Metadata:
        if not md.Role:
            continue
        kept = [r for r in md.Role if not _is_male_role(r)]
        removed += len(md.Role) - len(kept)
        md.Role = kept
    return removed


__all__ = ['PeopleManager', 'to_plex_roles', 'filter_male_actors', 'apply_name_aliases', 'find_photo', 'Gender', 'Role', 'PersonInput', 'ResolvedPerson']
