from __future__ import annotations

import asyncio
from typing import Any

from phoenixadult.clients.aggregators.data18 import data18_ref
from phoenixadult.clients.base import SceneDetail, SearchResult
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
)
from phoenixadult.registry import ResolvedSiteInfo, normalize_site_key
from phoenixadult.utils.genres import NormalizeGenresOptions, normalize_genres
from phoenixadult.utils.helpers.helpers import embed_subsite
from phoenixadult.utils.images.image_classifier import classify_image
from phoenixadult.utils.images.image_fetcher import fetch_dimensions
from phoenixadult.utils.images.image_referers import resolve_image_cookies, resolve_image_referers
from phoenixadult.utils.images.proxy import proxy_url
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.people import PeopleManager, to_plex_roles
from phoenixadult.utils.plex.rating_key import to_guid, to_rating_key
from phoenixadult.utils.processors.studio_name import normalize_studio
from phoenixadult.utils.processors.text_normalize import normalize_text
from phoenixadult.utils.processors.title_case import title_case, title_sort


def _year_of(date: str | None) -> int | None:
    return int(date[0:4]) if date and date[0:4].isdigit() else None


def _classify_artwork(valid: list[dict[str, Any]]) -> tuple[list[PlexImage], set[str]]:
    """Keep probed images with a servable class. An off-ratio portrait is still a usable cover, so it
    is kept and returned in the demoted set to sort behind the properly shaped ones."""
    images: list[PlexImage] = []
    demoted: set[str] = set()
    for p in valid:
        if p['image_class'] in ('coverPoster', 'background', 'backgroundSquare'):
            images.append(PlexImage(url=p['url'], type=p['image_class']))
        elif p['dims']['height'] > p['dims']['width']:
            images.append(PlexImage(url=p['url'], type='coverPoster'))
            demoted.add(p['url'])
        else:
            logger.debug(f'Image {p["dims"]["width"]}x{p["dims"]["height"]} unknown: {p["url"]}')
    return images, demoted


def _promote_missing_kinds(images: list[PlexImage], valid: list[dict[str, Any]], by_class: dict[str, list[dict[str, Any]]]) -> None:
    """Backstops for absent kinds: backgrounds (else everything) double as coverPoster,
    backgroundSquare doubles as background."""
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


def build_artwork(valid: list[dict[str, Any]]) -> list[PlexImage]:
    """Probed images -> the served image list: classify, backfill absent kinds, order. Shared with
    the Plex import so a recovered scene is typed exactly like a freshly scraped one."""
    by_class: dict[str, list[dict[str, Any]]] = {}
    for probed in valid:
        by_class.setdefault(probed['image_class'], []).append(probed)
    images, demoted = _classify_artwork(valid)
    _promote_missing_kinds(images, valid, by_class)
    _sort_artwork(images, valid, demoted)
    return images


def _sort_artwork(images: list[PlexImage], valid: list[dict[str, Any]], demoted: set[str] | None = None) -> None:
    """In-place order: kinds keep first-appearance order, largest area first within a kind, with
    off-ratio covers held back to the end of their kind."""
    area = {p['url']: p['dims']['width'] * p['dims']['height'] for p in valid}
    held_back = demoted or set()
    first_pos: dict[str, int] = {}
    for idx, img in enumerate(images):
        first_pos.setdefault(img.type, idx)
    images.sort(key=lambda img: (first_pos[img.type], img.url in held_back, -area.get(img.url, 0)))


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

        thumb, art, images_proxied = await self._resolve_artwork(detail, referers, cookies)
        plex_actors, plex_directors, plex_producers = await self._resolve_people(detail, referers, cookies)

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
            data18=PlexData18.model_validate(ref) if (ref := data18_ref(detail.data18_url)) else None,
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
            Genre=[PlexGenre(tag=tag) for tag in normalize_genres(detail.genres, NormalizeGenresOptions(title=clean_title, site_name=detail.studio))],
            Role=plex_actors,
            Director=plex_directors or None,
            Producer=plex_producers or None,
            Image=images_proxied,
            Collection=[PlexCollection(tag=tag) for tag in collections],
            Country=[PlexCountry(tag=c) for c in detail.countries] if detail.countries else None,
        )

    async def _probe_artwork(self, art: list[str], referers: list[str], cookies: list[str]) -> list[dict[str, Any]]:
        """Measure and classify each artwork URL; images whose dimensions can't be
        fetched drop out."""

        async def probe(raw_url: str) -> dict[str, Any] | None:
            dims = await fetch_dimensions(raw_url, referers, cookies)
            if not dims:
                return None
            result = classify_image(dims['width'], dims['height'])
            return {'url': raw_url, 'dims': dims, 'image_class': result.image_class}

        probed = await asyncio.gather(*(probe(u) for u in art))
        return [p for p in probed if p is not None]

    async def _resolve_artwork(self, detail: SceneDetail, referers: list[str], cookies: list[str]) -> tuple[str | None, str | None, list[PlexImage]]:
        valid = await self._probe_artwork(detail.art, referers, cookies)
        images = build_artwork(valid)

        thumb_raw = next((img.url for img in images if img.type == 'coverPoster'), None) or (detail.art[0] if detail.art else None)
        art_raw = next((img.url for img in images if img.type == 'background'), None) or (detail.art[1] if len(detail.art) > 1 else None)
        images_proxied = [PlexImage(url=self._proxy(img.url, referers, cookies) or img.url, type=img.type) for img in images]
        return self._proxy(thumb_raw, referers, cookies), self._proxy(art_raw, referers, cookies), images_proxied

    async def _resolve_people(self, detail: SceneDetail, referers: list[str], cookies: list[str]) -> tuple[list[PlexRole], list[PlexRole], list[PlexRole]]:
        people = PeopleManager()
        for a in detail.actors or []:
            if a.name:
                people.add_actor(a.name, a.photo_url, a.gender or '', a.role)  # type: ignore[arg-type]
        for d in detail.directors or []:
            if d.name:
                people.add_director(d.name, d.photo_url, d.role)
        for pr in detail.producers or []:
            if pr.name:
                people.add_producer(pr.name, pr.photo_url, pr.role)
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
    """Debug-log where each image in the served response points."""
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
