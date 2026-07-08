from __future__ import annotations

import time

from app.clients.base import SceneContext, SceneDetail
from app.mappers.metadata_mapper import MetadataMapper, log_served_images
from app.models.metadata import PlexMetadataResponse
from app.models.provider_info import ProviderInfo
from app.registry import find_site
from app.services.scraper_router import ScraperRouter
from app.utils import cache as metadata_cache
from app.utils.concurrency.coalescer import Coalescer
from app.utils.helpers.helpers import split_subsite
from app.utils.http.ssrf_guard import ensure_fetchable_url
from app.utils.logging.logger import logger
from app.utils.people import filter_male_actors
from app.utils.plex.media_type import provider_mount_path
from app.utils.plex.rating_key import parse_rating_key


def _stamp_keys(response: PlexMetadataResponse, provider: ProviderInfo) -> None:
    """Serve-time only — never baked into cache snapshots, so the mount path can change."""
    mount = provider_mount_path(provider)
    for md in response.MediaContainer.Metadata:
        md.key = f'{mount}/library/metadata/{md.ratingKey}'


def _log_served(response: PlexMetadataResponse, provider: ProviderInfo) -> None:
    for md in response.MediaContainer.Metadata:
        logger.info(
            provider.id,
            f'Serving ratingKey={md.ratingKey} key={md.key} title="{md.title}" date={md.originallyAvailableAt} '
            f'genres={len(md.Genre or [])} actors={len(md.Role or [])} images={len(md.Image or [])}',
        )
        logger.debug(provider.id, f'metadata response -> {md.model_dump_json(by_alias=True, exclude_none=True)}')


_MEMO_TTL_SECONDS = 60.0
_MEMO_MAX_ENTRIES = 512
# Refreshing the same scene this many times inside the window forces a full re-scrape
# (bypassing the memo and the on-disk snapshot) — an in-Plex "reload from upstream".
_REFRESH_WINDOW_SECONDS = 60.0
_REFRESH_FORCE_COUNT = 3


class MetadataService:
    def __init__(self) -> None:
        self._scraper = ScraperRouter()
        self._mapper = MetadataMapper()
        self._memo: dict[tuple[str, str, str], tuple[float, PlexMetadataResponse]] = {}
        self._coalesce: Coalescer[tuple[str, str, str], PlexMetadataResponse | None] = Coalescer()
        self._refresh_log: dict[tuple[str, str, str], list[float]] = {}

    def _force_refresh_due(self, key: tuple[str, str, str]) -> bool:
        """Count refreshes of one scene; True (and reset) once the threshold is hit inside
        the window. Only the metadata route calls this — never the /images sidecar."""
        now = time.monotonic()
        hits = [t for t in self._refresh_log.get(key, ()) if now - t < _REFRESH_WINDOW_SECONDS]
        hits.append(now)
        if len(hits) >= _REFRESH_FORCE_COUNT:
            self._refresh_log.pop(key, None)
            return True
        self._refresh_log[key] = hits
        return False

    async def get_metadata(self, rating_key: str, provider: ProviderInfo, language: str | None = None, is_refresh: bool = False) -> PlexMetadataResponse | None:
        # Plex requests /library/metadata/{key} and .../images back to back; the memo
        # serves both from one scrape and coalesces concurrent requests in flight.
        key = (rating_key, provider.id, language or '')
        force = is_refresh and self._force_refresh_due(key)
        if force:
            logger.info(provider.id, f'Force refresh ({_REFRESH_FORCE_COUNT}x within {_REFRESH_WINDOW_SECONDS:.0f}s) for ratingKey={rating_key} — re-scraping')
        hit = self._memo.get(key)
        if hit and not force and time.monotonic() - hit[0] < _MEMO_TTL_SECONDS:
            logger.debug(provider.id, f'memo hit for ratingKey={rating_key}')
            return hit[1]

        async def _run() -> PlexMetadataResponse | None:
            result = await self._fetch_metadata(rating_key, provider, language, force=force)
            if result is not None:
                self._memo[key] = (time.monotonic(), result)
                if len(self._memo) > _MEMO_MAX_ENTRIES:
                    cutoff = time.monotonic() - _MEMO_TTL_SECONDS
                    self._memo = {k: v for k, v in self._memo.items() if v[0] >= cutoff}
            return result

        return await self._coalesce.run(key, _run)

    async def _fetch_metadata(self, rating_key: str, provider: ProviderInfo, language: str | None = None, force: bool = False) -> PlexMetadataResponse | None:
        logger.info(provider.id, f'Update ratingKey={rating_key}')

        parsed = parse_rating_key(rating_key)
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

        scene_url, subsite = split_subsite(self._scraper.decode(cur_id))  # sub-site folded into the cur_id at search

        cached = None if force else metadata_cache.read(site.name, cur_id)
        response = PlexMetadataResponse.model_validate(cached) if cached is not None else None
        if response is not None and metadata_cache.data18_remap_needed(response, site.name, cur_id):
            logger.info(provider.id, f'data18 mapping changed for ratingKey={rating_key} — re-scraping')
            response = None  # fall through to a fresh scrape below

        if response is not None:

            async def _fetch_detail() -> SceneDetail | None:
                # Re-scrape the scene so backfill can try each person's scene image before
                # the external people sources. Only invoked when someone is imageless.
                if not scene_url:
                    return None
                try:
                    await ensure_fetchable_url(scene_url)
                except ValueError as err:
                    logger.warn(provider.id, f'backfill: refusing blocked sceneURL from ratingKey: {err}')
                    return None
                return await self._scraper.fetch_scene_detail(scene_url, site, SceneContext(language=language, subsite=subsite))

            changed = await metadata_cache.backfill_people_images(response, site.name, fetch_detail=_fetch_detail)
            if metadata_cache.reapply_text_rules(response, site.scraper_config.type):  # re-apply current text rules
                changed = True
            if metadata_cache.backfill_metadata_attrs(response):  # attrs added after the snapshot was written
                changed = True
                logger.info(provider.id, f'Backfilled metadata attrs for ratingKey={rating_key}')
            if changed:
                await metadata_cache.write(site.name, cur_id, response)
                logger.info(provider.id, f'Updated cached metadata for ratingKey={rating_key}')
            # Filter AFTER any cache write so the snapshot keeps every actor on disk.
            if removed := filter_male_actors(response):
                logger.info(provider.id, f'Male-actor filter: hid {removed} cached actor(s) from ratingKey={rating_key}')
            _stamp_keys(response, provider)
            log_served_images(response)
            logger.info(provider.id, f'Serving snapshot for ratingKey={rating_key}')
            _log_served(response, provider)
            return response

        if not scene_url:
            logger.warn(provider.id, f'Could not decode curID from ratingKey={rating_key}')
            return None

        try:
            await ensure_fetchable_url(scene_url)
        except ValueError as err:
            logger.warn(provider.id, f'Refusing blocked sceneURL from ratingKey: {err}')
            return None

        logger.info(provider.id, f'Fetching detail for site="{site.name}" id="{scene_url}"')

        detail = await self._scraper.fetch_scene_detail(scene_url, site, SceneContext(language=language, subsite=subsite))
        if not detail:
            logger.warn(provider.id, f'No scene detail returned for site="{site.name}" id="{scene_url}"')
            return None

        metadata = await self._mapper.to_metadata(detail, rating_key, provider.plex_identifier, parsed['release_date'], site, filename_site=subsite)

        response = PlexMetadataResponse.model_validate({'MediaContainer': {'identifier': provider.plex_identifier, 'size': 1, 'Metadata': [metadata]}})

        await metadata_cache.write(site.name, cur_id, response)

        # Filter AFTER the cache write so the snapshot keeps male actors (cached for faster
        # future gender resolution); only the served response hides them.
        if removed := filter_male_actors(response):
            logger.info(provider.id, f'Male-actor filter: hid {removed} actor(s) from ratingKey={rating_key}')
        _stamp_keys(response, provider)
        log_served_images(response)
        _log_served(response, provider)
        return response
