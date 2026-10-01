from __future__ import annotations

import asyncio
import json
from typing import Any

from phoenixadult.config import config, image_base_url
from phoenixadult.models.metadata import (
    PlexCollection,
    PlexCountry,
    PlexData18,
    PlexGenre,
    PlexImage,
    PlexMatchResult,
    PlexMetadata,
    PlexMetadataResponse,
    PlexRole,
    PlexSource,
)
from phoenixadult.models.scrape import SceneDetail, SearchResult
from phoenixadult.registry import ResolvedSiteInfo, find_site, normalize_site_key
from phoenixadult.utils.concurrency import gate
from phoenixadult.utils.concurrency.gate import loop_gate
from phoenixadult.utils.genres import NormalizeGenresOptions, normalize_genres
from phoenixadult.utils.helpers.data18 import data18_ref_with_extras
from phoenixadult.utils.helpers.ids import embed_subsite
from phoenixadult.utils.images.image_classifier import classify_image
from phoenixadult.utils.images.image_fetcher import content_digest, fetch_dimensions, pixel_digest
from phoenixadult.utils.images.image_referers import resolve_image_cookies, resolve_image_referers
from phoenixadult.utils.images.proxy import proxy_url
from phoenixadult.utils.logging.logger import logger, verbose_enabled
from phoenixadult.utils.people import PeopleResolver, to_plex_roles
from phoenixadult.utils.plex.rating_key import to_guid, to_rating_key
from phoenixadult.utils.processors.scene_link import is_api_url
from phoenixadult.utils.processors.studio_name import normalize_studio
from phoenixadult.utils.processors.text_normalize import normalize_text
from phoenixadult.utils.processors.title_case import title_case, title_sort


def _year_of(date: str | None) -> int | None:
    return int(date[0:4]) if date and date[0:4].isdigit() else None


def _source_of(detail: SceneDetail) -> PlexSource | None:
    url = detail.scene_url if detail.scene_url and detail.scene_url.startswith(('http://', 'https://')) else None
    data = detail.source_json
    if data is not None:
        try:
            json.dumps(data)
        except (TypeError, ValueError):
            data = None
    if url is None and data is None:
        return None
    kind = detail.source_kind or (('api' if is_api_url(url) else 'page') if url else None)
    return PlexSource(url=url, kind=kind, data=data)


def _classify_artwork(valid: list[dict[str, Any]], priority: set[str]) -> tuple[list[PlexImage], set[str]]:
    images: list[PlexImage] = []
    demoted: set[str] = set()
    for p in valid:
        flag = True if p['url'] in priority else None
        if p['image_class'] in ('coverPoster', 'background', 'backgroundSquare'):
            images.append(PlexImage(url=p['url'], type=p['image_class'], priority=flag))
        elif p['dims']['height'] > p['dims']['width']:
            images.append(PlexImage(url=p['url'], type='coverPoster', priority=flag))
            demoted.add(p['url'])
        else:
            logger.debug(f'Image {p["dims"]["width"]}x{p["dims"]["height"]} unknown: {p["url"]}')
    return images, demoted


def _promote_missing_kinds(images: list[PlexImage], valid: list[dict[str, Any]], by_class: dict[str, list[dict[str, Any]]]) -> None:
    has_poster = any(img.type == 'coverPoster' for img in images)
    has_background = any(img.type == 'background' for img in images)

    if not has_poster and valid:
        candidates = by_class.get('background', valid) if has_background else valid
        logger.info(f'No portrait posters; promoting {len(candidates)} of {len(valid)} image(s) to coverPoster')
        for p in candidates:
            images.append(PlexImage(url=p['url'], type='coverPoster'))

    if not has_background and (sq := by_class.get('backgroundSquare')):
        logger.info(f'No background; promoting {len(sq)} backgroundSquare image(s) to background')
        for p in sq:
            images.append(PlexImage(url=p['url'], type='background'))


def build_artwork(valid: list[dict[str, Any]], priority: set[str] | None = None) -> list[PlexImage]:
    by_class: dict[str, list[dict[str, Any]]] = {}
    for probed in valid:
        by_class.setdefault(probed['image_class'], []).append(probed)
    images, demoted = _classify_artwork(valid, priority or set())
    _promote_missing_kinds(images, valid, by_class)
    _sort_artwork(images, valid, demoted)
    return images


def _sort_artwork(images: list[PlexImage], valid: list[dict[str, Any]], demoted: set[str] | None = None) -> None:
    area = {p['url']: p['dims']['width'] * p['dims']['height'] for p in valid}
    held_back = demoted or set()
    first_pos: dict[str, int] = {}
    for idx, img in enumerate(images):
        first_pos.setdefault(img.type, idx)
    images.sort(key=lambda img: (first_pos[img.type], not img.priority, img.url in held_back, -area.get(img.url, 0)))


def _keep_first_by(probed: list[dict[str, Any]], keys: list[str | None]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    kept: list[dict[str, Any]] = []
    for entry, key in zip(probed, keys, strict=True):
        if key is not None:
            if key in seen:
                continue
            seen.add(key)
        kept.append(entry)
    return kept


def _shape(entry: dict[str, Any]) -> tuple[int, int]:
    return int(entry['dims']['width']), int(entry['dims']['height'])


def needs_pixel_check(entries: list[dict[str, Any]]) -> list[bool]:
    counts: dict[tuple[int, int], int] = {}
    for entry in entries:
        counts[_shape(entry)] = counts.get(_shape(entry), 0) + 1
    return [counts[_shape(entry)] > 1 for entry in entries]


def pixel_keys(entries: list[dict[str, Any]], digests: list[str | None]) -> list[str | None]:
    keys: list[str | None] = []
    for entry, digest in zip(entries, digests, strict=True):
        width, height = _shape(entry)
        keys.append(f'{width}x{height}:{digest}' if digest else None)
    return keys


async def _dedupe_artwork(probed: list[dict[str, Any]], cookies: list[str] | None = None) -> list[dict[str, Any]]:
    kept = _keep_first_by(probed, list(await asyncio.gather(*(content_digest(p['url'], cookies) for p in probed))))

    async def digest_if_ambiguous(entry: dict[str, Any], ambiguous: bool) -> str | None:
        return await pixel_digest(entry['url'], cookies) if ambiguous else None

    wanted = needs_pixel_check(kept)
    digests = list(await asyncio.gather(*(digest_if_ambiguous(entry, ambiguous) for entry, ambiguous in zip(kept, wanted, strict=True))))
    kept = _keep_first_by(kept, pixel_keys(kept, digests))

    if dropped := len(probed) - len(kept):
        logger.info(f'Dropped {dropped} duplicate image(s) of {len(probed)}')
    return kept


def _actor_names(detail: SceneDetail, resolved: list[PlexRole]) -> tuple[str, ...]:
    scraped = [a.name for a in detail.actors or [] if a.name]
    return tuple(dict.fromkeys([*scraped, *(r.tag for r in resolved if r.tag)]))


class MetadataMapper:
    def _proxy(self, url: str | None, referers: list[str] | None = None, cookies: list[str] | None = None, *, passthrough_local: bool = False) -> str | None:
        return proxy_url(url, config.base_url, referers, cookies, passthrough_local=passthrough_local)

    def to_match_result(
        self,
        raw: SearchResult,
        site_name: str,
        score: float,
        plex_identifier: str,
        date: str | None = None,
        scraper_type: str | None = None,
        filename_site: str | None = None,
    ) -> PlexMatchResult:
        search_sub = raw.subsite or filename_site
        search_sub = search_sub if search_sub and normalize_site_key(search_sub) != normalize_site_key(site_name) else None
        if search_sub and scraper_type:
            canonical = find_site(search_sub)
            if canonical is not None and canonical.scraper_config.type == scraper_type and normalize_site_key(canonical.name) == normalize_site_key(search_sub):
                site_name = canonical.name
                search_sub = None
        rating_key = to_rating_key(embed_subsite(raw.cur_id, search_sub), site_name, date)
        display_date = (raw.display_date or '').strip()
        label = normalize_studio(raw.subsite or filename_site or site_name)
        title = f'{title_case(raw.title, site_name=site_name, scraper_type=scraper_type)} [{label}]' + (f' {display_date}' if display_date else '')

        return PlexMatchResult(
            type='movie',
            ratingKey=rating_key,
            guid=to_guid(rating_key, plex_identifier),
            title=title,
            score=score,
            originallyAvailableAt=date or None,
            year=_year_of(date),
            contentRating='XXX',
            thumb=self._proxy(raw.thumb_url),
        )

    async def to_metadata(
        self,
        detail: SceneDetail,
        rating_key: str,
        plex_identifier: str,
        fallback_date: str | None = None,
        site: ResolvedSiteInfo | None = None,
        filename_site: str | None = None,
    ) -> PlexMetadata:
        clean_title = title_case(detail.title, site_name=detail.studio, scraper_type=site.scraper_config.type if site else None)
        logger.info(f'Artwork found: {len(detail.art)}')
        for u in detail.art:
            logger.info(f'Poster: {u}')

        site_referers = resolve_image_referers(site, detail.scene_url) if site else []
        referers = [detail.art_referer, *site_referers] if detail.art_referer else site_referers
        site_cookies = resolve_image_cookies(site) if site else []
        cookies = [detail.art_cookie, *site_cookies] if detail.art_cookie else site_cookies

        (thumb, art, images_proxied), (plex_actors, plex_directors, plex_producers) = await asyncio.gather(
            self._resolve_artwork(detail, referers, cookies), self._resolve_people(detail, referers, cookies)
        )

        effective_date = detail.release_date or fallback_date
        year = _year_of(effective_date)

        studio, tagline, collections = self._resolve_labels(detail, filename_site)

        return PlexMetadata(
            type='movie',
            ratingKey=rating_key,
            guid=to_guid(rating_key, plex_identifier),
            title=clean_title,
            titleSort=title_sort(clean_title),
            originalTitle=detail.original_title,
            summary=normalize_text(detail.summary) or None,
            tagline=tagline,
            data18=PlexData18.model_validate(ref) if (ref := data18_ref_with_extras(detail.data18_url)) else None,
            sourceRef=_source_of(detail),
            studio=studio,
            contentRating='XXX',
            isAdult=True,
            rating=detail.rating,
            audienceRating=detail.audience_rating,
            duration=detail.duration,
            originallyAvailableAt=effective_date or None,
            year=year,
            thumb=thumb,
            art=art,
            Genre=[
                PlexGenre(tag=tag)
                for tag in normalize_genres(
                    detail.genres,
                    NormalizeGenresOptions(title=clean_title, site_name=detail.studio, actors=_actor_names(detail, plex_actors)),
                )
            ],
            Role=plex_actors,
            Director=plex_directors or None,
            Producer=plex_producers or None,
            Image=images_proxied,
            Collection=[PlexCollection(tag=tag) for tag in collections],
            Country=[PlexCountry(tag=c) for c in detail.countries] if detail.countries else None,
        )

    async def _probe_artwork(self, art: list[str], referers: list[str], cookies: list[str]) -> list[dict[str, Any]]:

        sem = loop_gate('artwork-probe', gate.ARTWORK_PROBE)

        async def probe(raw_url: str) -> dict[str, Any] | None:
            async with sem:
                dims = await fetch_dimensions(raw_url, referers, cookies)
            if not dims:
                return None
            result = classify_image(dims['width'], dims['height'])
            return {'url': raw_url, 'dims': dims, 'image_class': result.image_class}

        probed = await asyncio.gather(*(probe(u) for u in art))
        return await _dedupe_artwork([p for p in probed if p is not None], cookies)

    async def _resolve_artwork(self, detail: SceneDetail, referers: list[str], cookies: list[str]) -> tuple[str | None, str | None, list[PlexImage]]:
        valid = await self._probe_artwork(detail.art, referers, cookies)
        images = build_artwork(valid, set(detail.art_priority))
        usable = [str(entry['url']) for entry in valid]
        if detail.art and not usable:
            logger.info(f'None of the {len(detail.art)} artwork url(s) could be read — leaving this scene without a poster')

        thumb_raw = next((img.url for img in images if img.type == 'coverPoster'), None) or (usable[0] if usable else None)
        art_raw = next((img.url for img in images if img.type == 'background'), None) or (usable[1] if len(usable) > 1 else None)
        images_proxied = [PlexImage(url=self._proxy(img.url, referers, cookies) or img.url, type=img.type, priority=img.priority) for img in images]
        return self._proxy(thumb_raw, referers, cookies), self._proxy(art_raw, referers, cookies), images_proxied

    async def _resolve_people(self, detail: SceneDetail, referers: list[str], cookies: list[str]) -> tuple[list[PlexRole], list[PlexRole], list[PlexRole]]:
        people = PeopleResolver()
        people.add_detail(detail)
        resolved = await people.resolve_all(studio=detail.studio, site_name=detail.studio, referers=referers, cookies=cookies)

        people_base = image_base_url()
        return (
            to_plex_roles(resolved['actors'], people_base, referers, cookies),
            to_plex_roles(resolved['directors'], people_base, referers, cookies),
            to_plex_roles(resolved['producers'], people_base, referers, cookies),
        )

    def _resolve_labels(self, detail: SceneDetail, filename_site: str | None) -> tuple[str, str | None, list[str]]:
        studio = normalize_studio(detail.studio)
        if detail.tagline:
            tagline = normalize_studio(detail.tagline)
            collections = list(dict.fromkeys(normalize_studio(c) for c in (detail.collections or [detail.tagline]) if c))
        elif filename_site and normalize_site_key(filename_site) != normalize_site_key(detail.studio):
            tagline = normalize_studio(filename_site)
            collections = [tagline]
        else:
            tagline = None
            collections = list(dict.fromkeys(normalize_studio(c) for c in (detail.collections or [detail.studio]) if c))
        if tagline and normalize_site_key(tagline) == normalize_site_key(studio):
            tagline = None
        return studio, tagline, collections


def log_served_images(response: PlexMetadataResponse, label: str = 'images') -> None:
    if verbose_enabled():
        logger.verbose(label, f'full response -> {response.model_dump_json(by_alias=True, exclude_none=True)}')
    logger.debug(label, f'people image base -> {image_base_url()}')

    for md in response.MediaContainer.Metadata:
        if md.thumb:
            logger.debug(label, f'thumb -> {md.thumb}')
        if md.art:
            logger.debug(label, f'art -> {md.art}')
        for img in md.Image or []:
            logger.debug(label, f'image[{img.type}] -> {img.url}')
        for r in (*(md.Role or []), *(md.Director or []), *(md.Producer or [])):
            if r.thumb:
                logger.debug(label, f'person "{r.tag}" -> {r.thumb}')
