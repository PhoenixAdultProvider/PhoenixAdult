from __future__ import annotations

from app.clients.base import SceneContext
from app.mappers.metadata_mapper import MetadataMapper
from app.models.metadata import PlexMetadataResponse
from app.models.provider_info import ProviderInfo
from app.registry import find_site
from app.routes.scraper_router import ScraperRouter
from app.services import metadata_cache
from app.utils.http.ssrf_guard import ensure_fetchable_url
from app.utils.logging.logger import logger


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
            logger.info(provider.id, f'Serving snapshot for ratingKey={rating_key}')
            return PlexMetadataResponse.model_validate(cached)

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
