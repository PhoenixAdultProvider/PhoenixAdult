from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from cachetools import TTLCache

from phoenixadult.clients import is_paced
from phoenixadult.config.env import env
from phoenixadult.mappers.metadata_mapper import MetadataMapper, log_served_images
from phoenixadult.models.metadata import PlexMetadataResponse
from phoenixadult.models.provider_info import ProviderInfo
from phoenixadult.models.scrape import SceneContext, SceneDetail
from phoenixadult.registry import ResolvedSiteInfo, canonical_site_display, find_site
from phoenixadult.services import scrape_queue, snapshot_backfill
from phoenixadult.services.provider_errors import MalformedRequestError, ProviderUnavailableError
from phoenixadult.services.scraper_router import ScraperRouter
from phoenixadult.utils.cache import layout as cache_layout
from phoenixadult.utils.cache import metadata as metadata_cache
from phoenixadult.utils.cache import people_backfill, scene_store, search_store, text_rules
from phoenixadult.utils.concurrency.coalescer import Coalescer
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.helpers.ids import split_subsite
from phoenixadult.utils.http.connectivity import begin_transport_watch, internet_reachable, transport_failures
from phoenixadult.utils.http.rate_limit_helper import PLEX_REQUEST_BUDGET, PacingDeferredError
from phoenixadult.utils.http.ssrf_guard import ensure_fetchable_url
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.people import filter_male_actors
from phoenixadult.utils.plex.media_type import provider_mount_path
from phoenixadult.utils.plex.rating_key import parse_rating_key


def queue_label(rating_key: str) -> str:
    return _queue_label(rating_key)


def _queue_label(rating_key: str) -> str:
    from phoenixadult.utils.helpers.ids import b64url_decode, b64url_encode

    parsed = parse_rating_key(rating_key)
    if not parsed or not parsed.get('site_name'):
        return rating_key
    site = canonical_site_display(parsed['site_name'] or '') or parsed['site_name']
    date = parsed.get('release_date')
    raw_cur = parsed.get('cur_id') or ''
    subsite: str | None = None
    try:
        payload, subsite = split_subsite(b64url_decode(raw_cur))
        plain_cur = b64url_encode(payload)
    except ValueError:
        plain_cur = raw_cur
    found = search_store.find_title(plain_cur)
    if found:
        title, result_site = found
        return f'{title} [{result_site or subsite or site}] {date}' if date else f'{title} [{result_site or subsite or site}]'
    branded = f'[{subsite or site}]'
    return f'{branded} {date}' if date else f'{branded} {raw_cur or rating_key}'


def _log_abandoned(task: asyncio.Task[PlexMetadataResponse | None]) -> None:
    if task.cancelled():
        return
    if err := task.exception():
        logger.warn('metadata', f'abandoned scrape failed: {err!r}')


def _stamp_keys(response: PlexMetadataResponse, provider: ProviderInfo) -> None:
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
        logger.verbose(provider.id, f'metadata response -> {md.model_dump_json(by_alias=True, exclude_none=True)}')


async def refresh_cached_snapshot(
    response: PlexMetadataResponse,
    site: ResolvedSiteInfo,
    cur_id: str,
    *,
    fetch_detail: Callable[[], Awaitable[SceneDetail | None]] | None = None,
    skip_data18: bool = False,
) -> bool:
    changed = snapshot_backfill.backfill_studio(response, site)
    locks = await run_in('store', scene_store.locks, cache_layout._hash(site.name, cur_id))
    if text_rules.reapply_text_rules(response, site.scraper_config.type, locked=set(locks['fields'])):
        changed = True
    if await run_in('store', metadata_cache.drop_stale_people_thumbs, response, site.name, cur_id):
        changed = True
    backfills = [people_backfill.backfill_people_images(response, site.name, fetch_detail=fetch_detail)]
    if not skip_data18:
        backfills.append(snapshot_backfill.backfill_data18(response, site.name))
    if any(await asyncio.gather(*backfills)):
        changed = True
    if people_backfill.backfill_metadata_attrs(response):
        changed = True
    if changed:
        await metadata_cache.write(site.name, cur_id, response)
    return changed


_MEMO_TTL_SECONDS = 60.0
_MEMO_MAX_ENTRIES = 512
_REFRESH_WINDOW_SECONDS = 60.0


class MetadataService:
    def __init__(self) -> None:
        self._scraper = ScraperRouter()
        self._mapper = MetadataMapper()
        self._memo: TTLCache[tuple[str, str, str], PlexMetadataResponse] = TTLCache(maxsize=_MEMO_MAX_ENTRIES, ttl=_MEMO_TTL_SECONDS)
        self._coalesce: Coalescer[tuple[str, str, str], PlexMetadataResponse | None] = Coalescer()
        self._refresh_log: dict[tuple[str, str, str], list[float]] = {}

    def _force_refresh_due(self, key: tuple[str, str, str]) -> bool:
        now = time.monotonic()
        hits = [t for t in self._refresh_log.get(key, ()) if now - t < _REFRESH_WINDOW_SECONDS]
        hits.append(now)
        if len(hits) >= env.refresh_force_count:
            self._refresh_log.pop(key, None)
            return True
        self._refresh_log[key] = hits
        return False

    async def get_metadata(self, rating_key: str, provider: ProviderInfo, language: str | None = None, is_refresh: bool = False) -> PlexMetadataResponse | None:
        begin_transport_watch()
        key = (rating_key, provider.id, language or '')
        force = is_refresh and self._force_refresh_due(key)
        if force:
            logger.info(
                provider.id, f'Force refresh ({env.refresh_force_count}x within {_REFRESH_WINDOW_SECONDS:.0f}s) for ratingKey={rating_key} — re-scraping'
            )
        hit = self._memo.get(key)
        if hit is not None and not force:
            logger.debug(provider.id, f'memo hit for ratingKey={rating_key}')
            return hit

        async def _run() -> PlexMetadataResponse | None:
            result = await self._fetch_metadata(rating_key, provider, language, force=force)
            if result is not None:
                self._memo[key] = result
            return result

        task = asyncio.ensure_future(self._coalesce.run(key, _run))
        try:
            return await asyncio.wait_for(asyncio.shield(task), PLEX_REQUEST_BUDGET)
        except TimeoutError:
            logger.warn(
                provider.id,
                f'Update exceeded the {PLEX_REQUEST_BUDGET:.0f}s Plex budget for ratingKey={rating_key} — scrape continues in background',
            )
            task.add_done_callback(_log_abandoned)
            raise ProviderUnavailableError('scrape exceeded the Plex request budget — retry later') from None

    async def _scrape(
        self,
        rating_key: str,
        provider: ProviderInfo,
        site: ResolvedSiteInfo,
        scene_url: str,
        subsite: str | None,
        release_date: str | None,
        language: str | None,
        allow_slow: bool = False,
    ) -> PlexMetadataResponse | None:
        try:
            await ensure_fetchable_url(scene_url)
        except ValueError as err:
            logger.warn(provider.id, f'Refusing blocked sceneURL from ratingKey: {err}')
            return None

        logger.info(provider.id, f'Fetching detail for site="{site.name}" id="{scene_url}"')
        detail = await self._scraper.fetch_scene_detail(scene_url, site, SceneContext(language=language, subsite=subsite, allow_slow=allow_slow))
        if not detail:
            logger.warn(provider.id, f'No scene detail returned for site="{site.name}" id="{scene_url}"')
            return None

        metadata = await self._mapper.to_metadata(detail, rating_key, provider.plex_identifier, release_date, site, filename_site=subsite)
        return PlexMetadataResponse.model_validate({'MediaContainer': {'identifier': provider.plex_identifier, 'size': 1, 'Metadata': [metadata]}})

    def _finalize(self, response: PlexMetadataResponse, provider: ProviderInfo, rating_key: str, *, cached: bool) -> PlexMetadataResponse:
        if removed := filter_male_actors(response):
            noun = 'cached actor(s)' if cached else 'actor(s)'
            logger.info(provider.id, f'Male-actor filter: hid {removed} {noun} from ratingKey={rating_key}')
        _stamp_keys(response, provider)
        log_served_images(response)
        _log_served(response, provider)
        return response

    def drop_memo(self, rating_key: str, provider: ProviderInfo) -> None:
        for key in [k for k in self._memo if k[0] == rating_key and k[1] == provider.id]:
            self._memo.pop(key, None)

    def queue_snapshot(
        self, rating_key: str, provider: ProviderInfo, language: str | None, label: str | None = None, force: bool = False, rescrape: bool = False
    ) -> bool:

        async def _job() -> None:
            await self._fetch_metadata(rating_key, provider, language, force=rescrape, allow_slow=True)

        parsed = parse_rating_key(rating_key)
        if not force and parsed and parsed['site_name'] and parsed['cur_id'] and metadata_cache.read(parsed['site_name'], parsed['cur_id']) is not None:
            logger.debug(provider.id, f'snapshot already cached for ratingKey={rating_key} — not queueing')
            return False

        site = find_site(parsed['site_name'] or '') if parsed else None
        label = label or _queue_label(rating_key)
        replay = {'kind': 'update', 'provider': provider.id, 'rating_key': rating_key, 'language': language, 'label': label, 'rescrape': rescrape}
        return scrape_queue.enqueue(
            f'{provider.id}:{rating_key}',
            _job,
            kind='update',
            label=label,
            replay=replay,
            paced=bool(site and is_paced(site.scraper_config.type)),
        )

    def _queue_background(self, rating_key: str, provider: ProviderInfo, language: str | None, wait_seconds: float) -> None:
        queued = self.queue_snapshot(rating_key, provider, language, force=True)
        state = 'queued background scrape' if queued else 'background scrape already queued'
        logger.info(provider.id, f'Pacing defers ratingKey={rating_key} (~{wait_seconds:.0f}s wait) — {state}; a later refresh serves it from the snapshot')

    async def _pull_data18_enrichment(
        self,
        rating_key: str,
        provider: ProviderInfo,
        site: ResolvedSiteInfo,
        cur_id: str,
        scene_url: str,
        subsite: str | None,
        release_date: str | None,
        language: str | None,
        allow_slow: bool,
    ) -> PlexMetadataResponse | None:
        logger.info(provider.id, f'No data18 ref for ratingKey={rating_key} — attempting enrichment pull')
        try:
            fresh = await self._scrape(rating_key, provider, site, scene_url, subsite, release_date, language, allow_slow=allow_slow)
        except PacingDeferredError:
            fresh = None
            logger.info(provider.id, f'Enrichment pull deferred by pacing for ratingKey={rating_key} — serving cached snapshot')
        if fresh is not None and fresh.MediaContainer.Metadata[0].data18 is not None:
            await metadata_cache.write(site.name, cur_id, fresh)
            logger.info(provider.id, f'data18 enrichment pulled for ratingKey={rating_key}')
            return fresh
        logger.info(provider.id, f'No data18 match on pull for ratingKey={rating_key} — serving cached snapshot')
        return None

    async def _serve_cached(
        self,
        response: PlexMetadataResponse,
        rating_key: str,
        provider: ProviderInfo,
        site: ResolvedSiteInfo,
        cur_id: str,
        scene_url: str,
        subsite: str | None,
        language: str | None,
        skip_data18: bool,
    ) -> PlexMetadataResponse:

        async def _fetch_detail() -> SceneDetail | None:
            if not scene_url:
                return None
            try:
                await ensure_fetchable_url(scene_url)
            except ValueError as err:
                logger.warn(provider.id, f'backfill: refusing blocked sceneURL from ratingKey: {err}')
                return None
            return await self._scraper.fetch_scene_detail(scene_url, site, SceneContext(language=language, subsite=subsite))

        if await refresh_cached_snapshot(response, site, cur_id, fetch_detail=_fetch_detail, skip_data18=skip_data18):
            logger.info(provider.id, f'Updated cached metadata for ratingKey={rating_key}')
        logger.info(provider.id, f'Serving snapshot for ratingKey={rating_key}')
        return self._finalize(response, provider, rating_key, cached=True)

    async def _scrape_and_store(
        self,
        rating_key: str,
        provider: ProviderInfo,
        site: ResolvedSiteInfo,
        cur_id: str,
        scene_url: str,
        subsite: str | None,
        release_date: str | None,
        language: str | None,
        allow_slow: bool,
    ) -> PlexMetadataResponse | None:
        try:
            fresh = await self._scrape(rating_key, provider, site, scene_url, subsite, release_date, language, allow_slow=allow_slow)
        except PacingDeferredError as err:
            self._queue_background(rating_key, provider, language, err.wait_seconds)
            if allow_slow:
                return None
            raise ProviderUnavailableError('scrape deferred by pacing — a later refresh serves it from the snapshot') from None
        if fresh is None:
            if not allow_slow and transport_failures() and not await internet_reachable():
                raise ProviderUnavailableError('no network connectivity')
            return None
        await metadata_cache.write(site.name, cur_id, fresh)
        return self._finalize(fresh, provider, rating_key, cached=False)

    async def _fetch_metadata(
        self, rating_key: str, provider: ProviderInfo, language: str | None = None, force: bool = False, allow_slow: bool = False
    ) -> PlexMetadataResponse | None:
        logger.info(provider.id, f'Update ratingKey={rating_key}')

        parsed = parse_rating_key(rating_key)
        if not parsed:
            logger.warn(provider.id, f'Unrecognised ratingKey format: {rating_key}')
            raise MalformedRequestError(f'unrecognised ratingKey format: {rating_key}')

        site_name = parsed['site_name']
        cur_id = parsed['cur_id']
        if not (site_name and cur_id):
            logger.warn(provider.id, f'Incomplete ratingKey (missing siteName/curID): {rating_key}')
            raise MalformedRequestError(f'incomplete ratingKey: {rating_key}')

        site = find_site(site_name)
        if not site:
            logger.warn(provider.id, f'No site found for siteName "{site_name}" from ratingKey')
            raise MalformedRequestError(f'no registry site for siteName "{site_name}"')

        scene_url, subsite = split_subsite(self._scraper.decode(cur_id))

        cached = None if force else await run_in('store', metadata_cache.read, site.name, cur_id)
        response = PlexMetadataResponse.model_validate(cached) if cached is not None else None
        if response is not None and metadata_cache.data18_remap_needed(response, site.name):
            logger.info(provider.id, f'data18 mapping changed for ratingKey={rating_key} — re-scraping')
            response = None

        pull_attempted = False
        if response is not None and scene_url and metadata_cache.data18_backfill_needed(response, site.name):
            pull_attempted = True
            enriched = await self._pull_data18_enrichment(rating_key, provider, site, cur_id, scene_url, subsite, parsed['release_date'], language, allow_slow)
            if enriched is not None:
                return self._finalize(enriched, provider, rating_key, cached=False)

        if response is not None:
            return await self._serve_cached(response, rating_key, provider, site, cur_id, scene_url, subsite, language, skip_data18=pull_attempted)

        if not scene_url:
            logger.warn(provider.id, f'Could not decode curID from ratingKey={rating_key}')
            raise MalformedRequestError(f'undecodable curID in ratingKey={rating_key}')

        return await self._scrape_and_store(rating_key, provider, site, cur_id, scene_url, subsite, parsed['release_date'], language, allow_slow)
