from __future__ import annotations

import asyncio
import re
from typing import Any

from app.clients.base import SceneDetail, SearchResult
from app.config import config, people_image_base
from app.models.metadata import (
    PlexCollection,
    PlexCountry,
    PlexGenre,
    PlexImage,
    PlexMatchResult,
    PlexMetadata,
    PlexMetadataResponse,
)
from app.registry import ResolvedSiteInfo
from app.utils.genres import NormalizeGenresOptions, normalize_genres
from app.utils.images.image_classifier import classify_image
from app.utils.images.image_fetcher import fetch_dimensions
from app.utils.images.image_referers import resolve_image_cookies, resolve_image_referers
from app.utils.images.proxy import proxy_url
from app.utils.logging.logger import logger
from app.utils.people import PeopleManager, to_plex_roles
from app.utils.plex.rating_key import to_guid, to_rating_key
from app.utils.processors.title_case import title_case

_ARTICLE_RE = re.compile(r'^(the|a|an)\s+', re.IGNORECASE)


def _title_sort(title: str) -> str | None:
    stripped = _ARTICLE_RE.sub('', title).strip()
    return stripped if stripped and stripped != title else None


class MetadataMapper:
    def _proxy(self, url: str | None, referers: list[str] | None = None, cookies: list[str] | None = None) -> str | None:
        return proxy_url(url, config.base_url, referers, cookies)

    def to_match_result(
        self, raw: SearchResult, site_name: str, score: float, plex_identifier: str, date: str | None = None, scraper_type: str | None = None
    ) -> PlexMatchResult:
        rating_key = to_rating_key(raw.cur_id, site_name, date)
        display_date = (raw.display_date or '').strip()
        title = f'{title_case(raw.title, site_name=site_name, scraper_type=scraper_type)} [{site_name}]' + (f' {display_date}' if display_date else '')
        return PlexMatchResult(
            type='movie',
            ratingKey=rating_key,
            guid=to_guid(rating_key, plex_identifier),
            title=title,
            score=score,
            originallyAvailableAt=date or None,
            year=int(date[0:4]) if date else None,
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
    ) -> PlexMetadata:
        clean_title = title_case(detail.title, site_name=detail.studio, scraper_type=site.scraper_config.type if site else None)
        logger.info(f'Artwork found: {len(detail.raw_image_urls)}')
        for u in detail.raw_image_urls:
            logger.info(f'Poster: {u}')

        site_referers = resolve_image_referers(site, detail.scene_url) if site else []
        referers = [detail.raw_image_referer, *site_referers] if detail.raw_image_referer else site_referers
        site_cookies = resolve_image_cookies(site) if site else []
        cookies = [detail.raw_image_cookie, *site_cookies] if detail.raw_image_cookie else site_cookies

        async def probe(raw_url: str) -> dict[str, Any] | None:
            dims = await fetch_dimensions(raw_url, referers, cookies)
            if not dims:
                return None
            result = classify_image(dims['width'], dims['height'])
            return {'url': raw_url, 'dims': dims, 'image_class': result.image_class}

        probed = await asyncio.gather(*(probe(u) for u in detail.raw_image_urls))
        valid = [p for p in probed if p is not None]

        images: list[PlexImage] = []
        for p in valid:
            if p['image_class'] in ('coverPoster', 'background'):
                images.append(PlexImage(url=p['url'], type=p['image_class']))
            else:
                logger.debug(f'Image {p["dims"]["width"]}x{p["dims"]["height"]} unknown: {p["url"]}')

        has_poster = any(img.type == 'coverPoster' for img in images)
        if not has_poster and valid:
            logger.info(f'No portrait posters; promoting all {len(valid)} image(s) to coverPoster')
            for p in valid:
                images.append(PlexImage(url=p['url'], type='coverPoster'))

        thumb_raw = next((img.url for img in images if img.type == 'coverPoster'), None) or (detail.raw_image_urls[0] if detail.raw_image_urls else None)
        art_raw = next((img.url for img in images if img.type == 'background'), None) or (detail.raw_image_urls[1] if len(detail.raw_image_urls) > 1 else None)
        thumb = self._proxy(thumb_raw, referers, cookies)
        art = self._proxy(art_raw, referers, cookies)
        images_proxied = [PlexImage(url=self._proxy(img.url, referers, cookies) or img.url, type=img.type) for img in images]

        people = PeopleManager()
        for a in detail.actors or []:
            if a.name:
                people.add_actor(a.name, a.photo_url, a.gender or '')  # type: ignore[arg-type]
        for d in detail.directors or []:
            if d.name:
                people.add_director(d.name, d.photo_url)
        for pr in detail.producers or []:
            if pr.name:
                people.add_producer(pr.name, pr.photo_url)
        resolved = await people.resolve_all(studio=detail.studio, site_name=detail.studio, referers=referers, cookies=cookies)

        people_base = people_image_base()
        plex_actors = to_plex_roles(resolved['actors'], people_base, referers, cookies)
        plex_directors = to_plex_roles(resolved['directors'], people_base, referers, cookies)
        plex_producers = to_plex_roles(resolved['producers'], people_base, referers, cookies)

        effective_date = detail.release_date or fallback_date
        year = int(effective_date[0:4]) if effective_date else None

        collections = detail.collections if detail.collections else [detail.studio]

        return PlexMetadata(
            type='movie',
            ratingKey=rating_key,
            guid=to_guid(rating_key, plex_identifier),
            title=clean_title,
            titleSort=_title_sort(clean_title),
            originalTitle=detail.original_title,
            summary=detail.summary,
            tagline=detail.tagline,
            studio=detail.studio,
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


def log_served_images(response: PlexMetadataResponse, label: str = 'images') -> None:
    """Debug-log where each image in the served response points. Fires for both cached
    and freshly-scraped responses; URLs pass through the redaction filter, so IP literals
    are always scrubbed. People images use people_image_base(); poster/art use base_url.
    At LOG_LEVEL=verbose it also dumps the full response JSON exactly as sent to Plex."""
    logger.verbose(label, f'full response -> {response.model_dump_json(by_alias=True, exclude_none=True)}')
    logger.debug(label, f'people image base -> {people_image_base()}')
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
