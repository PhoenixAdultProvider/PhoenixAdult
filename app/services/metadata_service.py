from __future__ import annotations

from collections.abc import Callable

from app.clients.base import SceneContext
from app.config import config
from app.mappers.metadata_mapper import MetadataMapper
from app.models.metadata import PlexMetadataResponse, PlexRole
from app.models.provider_info import ProviderInfo
from app.registry import find_site
from app.routes.scraper_router import ScraperRouter
from app.services import metadata_cache
from app.utils.http.ssrf_guard import ensure_fetchable_url
from app.utils.logging.logger import logger
from app.utils.people import PeopleManager, to_plex_roles


class MetadataService:
    def __init__(self) -> None:
        self._scraper = ScraperRouter()
        self._mapper = MetadataMapper()

    async def get_metadata(self, rating_key: str, provider: ProviderInfo, language: str | None = None) -> PlexMetadataResponse | None:
        logger.info(provider.id, f'Update ratingKey={rating_key}')

        parsed = self._mapper.parse_rating_key(rating_key)
        if not parsed:
            logger.warn(provider.id, f'Unrecognised ratingKey format: {rating_key}')
            return None

        site_name = parsed['site_name']
        cur_id = parsed['cur_id']
        assert site_name and cur_id

        site = find_site(site_name)
        if not site:
            logger.warn(provider.id, f'No site found for siteName "{site_name}" from ratingKey')
            return None

        cached = metadata_cache.read(site.name, cur_id)
        if cached is not None:
            response = PlexMetadataResponse.model_validate(cached)
            if await self._backfill_people_images(response, site.name):
                await metadata_cache.write(site.name, cur_id, response)
                logger.info(provider.id, f'Backfilled missing cast/crew image(s) for ratingKey={rating_key}')
            logger.info(provider.id, f'Serving snapshot for ratingKey={rating_key}')
            return response

        scene_url = self._scraper.decode(cur_id)
        if not scene_url:
            logger.warn(provider.id, f'Could not decode curID from ratingKey={rating_key}')
            return None

        try:
            await ensure_fetchable_url(scene_url)
        except ValueError as err:
            logger.warn(provider.id, f'Refusing blocked sceneURL from ratingKey: {err}')
            return None

        logger.info(provider.id, f'Fetching detail for site="{site.name}" id="{scene_url}"')

        detail = await self._scraper.fetch_scene_detail(scene_url, site, SceneContext(language=language))
        if not detail:
            logger.warn(provider.id, f'No scene detail returned for site="{site.name}" id="{scene_url}"')
            return None

        metadata = await self._mapper.to_metadata(detail, rating_key, provider.plex_identifier, parsed['release_date'], site)

        response = PlexMetadataResponse.model_validate({'MediaContainer': {'identifier': provider.plex_identifier, 'size': 1, 'Metadata': [metadata]}})

        await metadata_cache.write(site.name, cur_id, response)

        return response

    async def _backfill_people_images(self, response: PlexMetadataResponse, site_name: str) -> bool:
        """Retry resolving headshots for cached cast / director / producer entries with no thumb.

        Best-effort (never breaks a cache serve) and self-healing — once an image
        is found the snapshot is re-written, so only still-imageless people retry.
        """
        try:
            md = response.MediaContainer.Metadata[0]
        except (AttributeError, IndexError):
            return False

        people = PeopleManager()
        # (entries on the snapshot, how to enqueue one, the resolve_all() output key)
        groups: list[tuple[list[PlexRole], Callable[[PlexRole], None], str]] = [
            (md.Role or [], lambda r: people.add_actor(r.tag, '', r.gender or ''), 'actors'),  # type: ignore[arg-type]
            (md.Director or [], lambda r: people.add_director(r.tag, ''), 'directors'),
            (md.Producer or [], lambda r: people.add_producer(r.tag, ''), 'producers'),
        ]

        any_missing = False
        for entries, add, _ in groups:
            for r in entries:
                if not r.thumb and r.tag:
                    add(r)
                    any_missing = True
        if not any_missing:
            return False

        try:
            resolved = await people.resolve_all(studio=md.studio or '', site_name=site_name)
        except Exception as err:  # noqa: BLE001 — backfill must never break the serve
            logger.warn('meta-cache', f'people-image backfill failed: {err}')
            return False

        changed = False
        for entries, _, key in groups:
            by_tag = {p.tag: p for p in to_plex_roles(resolved[key], config.base_url) if p.thumb}
            for r in entries:
                if not r.thumb and r.tag in by_tag:
                    resolved_role = by_tag[r.tag]
                    r.thumb = resolved_role.thumb
                    r.gender = r.gender or resolved_role.gender
                    changed = True
        return changed
