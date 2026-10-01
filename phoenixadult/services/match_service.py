from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import quote

from cachetools import TTLCache

from phoenixadult.clients import is_paced
from phoenixadult.config.env import env
from phoenixadult.mappers.metadata_mapper import MetadataMapper
from phoenixadult.models.metadata import PlexMatchResponse, PlexMatchResult
from phoenixadult.models.provider_info import ProviderInfo
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import canonical_site_display, find_site
from phoenixadult.services import scrape_queue
from phoenixadult.services.metadata_service import MetadataService
from phoenixadult.services.provider_errors import MalformedRequestError, ProviderUnavailableError
from phoenixadult.services.scraper_router import ScraperRouter
from phoenixadult.utils.cache import search_store
from phoenixadult.utils.concurrency.coalescer import Coalescer
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.helpers.dates import format_duration
from phoenixadult.utils.helpers.ids import unpack_cur_id
from phoenixadult.utils.helpers.scoring import date_distance_score, title_distance_score
from phoenixadult.utils.http.connectivity import begin_transport_watch, internet_reachable, transport_failures
from phoenixadult.utils.http.rate_limit_helper import PLEX_REQUEST_BUDGET, PacingDeferredError
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.plex.responses import empty_media_container, media_container
from phoenixadult.utils.processors.actor_strip import best_title_score
from phoenixadult.utils.processors.filename_parser import get_site_name_from_registry
from phoenixadult.utils.processors.search_query import build_search_pieces


@dataclass
class MatchRequest:
    type: int
    title: str | None = None
    year: int | None = None
    guid: str | None = None
    filename: str | None = None
    manual: int | None = None
    includeAdult: int | None = None
    duration: int | None = None
    ohash: str | None = None


_SEARCH_MEMO_TTL = 900.0
_SEARCH_MEMO_MAX = 512


def _result_scene_id(result: SearchResult) -> str | None:
    try:
        return unpack_cur_id(result.cur_id).get('head')
    except ValueError:
        return None


def _live_score(result: SearchResult, search_data: SearchContext) -> float:
    if search_data.scene_id and _result_scene_id(result) == search_data.scene_id:
        return 100.0
    if search_data.search_date and result.display_date and result.display_date != search_data.search_date:
        return float(date_distance_score(search_data.search_date, result.display_date))
    return float(best_title_score(search_data.title, result.title, search_data.site_info))


def _live_scores(results: list[SearchResult], search_data: SearchContext) -> list[SearchResult]:
    rescored = [replace(result, score=_live_score(result, search_data)) for result in results]
    rescored.sort(key=lambda r: r.score or 0.0, reverse=True)
    return rescored


AUTO_MATCH_SCORE = 100


def auto_match(results: list[PlexMatchResult]) -> tuple[PlexMatchResult | None, str]:
    perfect = [r for r in results if (r.score or 0) >= AUTO_MATCH_SCORE]
    if not perfect:
        return None, f'no perfect (>={AUTO_MATCH_SCORE}) result — returning empty'
    top = perfect[0].score or 0
    tied = [r for r in perfect if (r.score or 0) == top]
    if len(tied) > 1:
        return None, f'{len(tied)} results tied at {top} — ambiguous, returning empty'
    return tied[0], f'serving "{tied[0].title}" (score={top})'


class MatchService:
    def __init__(self, metadata_service: MetadataService | None = None) -> None:
        self._scraper = ScraperRouter()
        self._mapper = MetadataMapper()
        self.metadata_service = metadata_service
        self._search_memo: TTLCache[tuple[str, str, str, str, str], list[SearchResult]] = TTLCache(maxsize=_SEARCH_MEMO_MAX, ttl=_SEARCH_MEMO_TTL)
        self._search_coalesce: Coalescer[tuple[str, str, str, str, str], list[SearchResult] | None] = Coalescer()

    def _memo_key(self, search_data: SearchContext) -> tuple[str, str, str, str, str]:
        return (
            search_data.site_info.name,
            search_store.fold_query(search_data.title),
            search_data.search_date or '',
            search_data.scene_id or '',
            search_data.language or '',
        )

    def _is_paced(self, search_data: SearchContext) -> bool:
        return is_paced(search_data.site_info.scraper_config.type)

    async def _search_results(self, search_data: SearchContext, provider: ProviderInfo, allow_slow: bool = False) -> list[SearchResult] | None:
        key = self._memo_key(search_data)
        hit = self._search_memo.get(key)
        if hit is not None:
            logger.info(provider.id, f'search memo hit for "{search_data.title}" on {search_data.site_info.name}')
            return hit

        paced = self._is_paced(search_data)
        if paced:
            stored = await run_in('store', search_store.load, key)
            if stored is not None:
                logger.info(provider.id, f'search store hit for "{search_data.title}" on {search_data.site_info.name}')
                stored = _live_scores(stored, search_data)
            else:
                stored = await run_in('store', search_store.load_similar, key)
                if stored is not None:
                    logger.info(provider.id, f'search store substring hit for "{search_data.title}" on {search_data.site_info.name} (renamed file)')
                    stored = _live_scores(stored, search_data)
                    await run_in('store', search_store.save, key, stored)
            if stored is not None:
                self._search_memo[key] = stored
                return stored

        search_data.allow_slow = allow_slow

        async def _run() -> list[SearchResult] | None:
            raw = await self._scraper.search(search_data)
            if raw is not None and (raw or not transport_failures()):
                if raw:
                    self._search_memo[key] = raw
                if paced:
                    await run_in('store', search_store.save, key, raw)
            return raw

        return await self._search_coalesce.run(key, _run)

    def requeue_search(self, replay: dict[str, Any], provider: ProviderInfo) -> None:
        site = find_site(str(replay.get('search_site') or ''))
        if site is None:
            return
        title = str(replay.get('title') or '')
        ctx = SearchContext(
            title=title,
            encoded=quote(title, safe=''),
            search_site=str(replay.get('search_site') or ''),
            site_info=site,
            search_date=replay.get('date'),
            language=replay.get('language'),
            scene_id=replay.get('scene_id'),
        )
        self._queue_background_search(ctx, provider, 0.0)

    def _chain_perfect_match(self, results: list[SearchResult], search_data: SearchContext, provider: ProviderInfo) -> None:
        if self.metadata_service is None:
            return
        site = search_data.site_info
        filename_site = canonical_site_display(search_data.search_site)
        raws: dict[str, SearchResult] = {}
        mapped: list[PlexMatchResult] = []
        for raw in {r.cur_id: r for r in results}.values():
            score = raw.score if raw.score is not None else title_distance_score(search_data.title, raw.title)
            if score < AUTO_MATCH_SCORE:
                continue
            match = self._mapper.to_match_result(
                raw,
                site.name,
                score,
                provider.plex_identifier,
                raw.release_date or None,
                scraper_type=site.scraper_config.type,
                filename_site=filename_site,
            )
            raws[match.ratingKey] = raw
            mapped.append(match)
        mapped.sort(key=lambda m: m.score or 0, reverse=True)
        chosen, _why = auto_match(mapped)
        if chosen is None:
            return
        if self.metadata_service.queue_snapshot(chosen.ratingKey, provider, search_data.language, label=chosen.title):
            logger.info(provider.id, f'Perfect background match "{raws[chosen.ratingKey].title}" on {site.name} — chained snapshot scrape {chosen.ratingKey}')

    def _queue_background_search(self, search_data: SearchContext, provider: ProviderInfo, wait_seconds: float) -> None:

        async def _job() -> None:
            results = await self._search_results(search_data, provider, allow_slow=True)
            if results:
                self._chain_perfect_match(results, search_data, provider)

        key = ':'.join(('search', provider.id, *self._memo_key(search_data)))
        replay = {
            'kind': 'search',
            'provider': provider.id,
            'search_site': search_data.search_site,
            'title': search_data.title,
            'date': search_data.search_date,
            'scene_id': search_data.scene_id,
            'language': search_data.language,
        }
        queued = scrape_queue.enqueue(
            key,
            _job,
            kind='search',
            label=f'{search_data.site_info.name} — {search_data.title}',
            replay=replay,
            paced=self._is_paced(search_data),
        )
        state = 'queued background search' if queued else 'background search already queued'
        logger.info(
            provider.id,
            f'Pacing defers search "{search_data.title}" on {search_data.site_info.name} (~{wait_seconds:.0f}s wait) — {state}; '
            f'a later scan serves it from the search store',
        )

    async def match(self, req: MatchRequest, provider: ProviderInfo, language: str | None = None) -> PlexMatchResponse:
        begin_transport_watch()
        try:
            return await asyncio.wait_for(self._match(req, provider, language), PLEX_REQUEST_BUDGET)
        except TimeoutError:
            logger.warn(provider.id, f'Search exceeded the {PLEX_REQUEST_BUDGET:.0f}s Plex budget (title={req.title!r} filename={req.filename!r})')
            raise ProviderUnavailableError('search exceeded the Plex request budget — retry later') from None

    async def _match(self, req: MatchRequest, provider: ProviderInfo, language: str | None = None) -> PlexMatchResponse:
        is_manual = req.manual == 1
        include_adult = req.includeAdult == 1

        logger.info(provider.id, 'Match', title=req.title, filename=req.filename)

        parse_source = req.filename or req.title

        if not include_adult or (env.disable_auto_match and not is_manual):
            logger.info(
                provider.id,
                f'match suppressed (DISABLE_AUTO_MATCH={env.disable_auto_match_raw}, manual={is_manual}, includeAdult={include_adult})',
            )
            return self._empty(provider)

        if not parse_source:
            raise MalformedRequestError('no title or filename to parse')

        parsed = get_site_name_from_registry(parse_source, lambda token: find_site(token) is not None)
        if not parsed:
            logger.warn(provider.id, f'Could not parse: "{parse_source}"')
            return self._empty(provider)

        site = find_site(parsed.site_token)
        assert site is not None
        if site.provider_id != provider.id:
            logger.warn(provider.id, f'Site "{site.name}" belongs to "{site.provider_id}" — skip')
            return self._empty(provider)

        pieces = build_search_pieces(site.content_type, parsed)
        if not pieces.query:
            return self._empty(provider)

        search_data = SearchContext(
            title=pieces.query,
            encoded=quote(pieces.query, safe=''),
            search_site=parsed.site_token,
            site_info=site,
            search_date=parsed.date or None,
            year=req.year,
            duration=format_duration(req.duration),
            ohash=req.ohash,
            language=language,
            scene_id=pieces.scene_id,
            full_title=pieces.full_title,
        )

        try:
            raw_results = await self._search_results(search_data, provider)
        except PacingDeferredError as err:
            self._queue_background_search(search_data, provider, err.wait_seconds)
            raise ProviderUnavailableError('search deferred by pacing — a later scan serves it from the search store') from None
        if raw_results is None:
            logger.warn(provider.id, f'No scraper registered for type "{site.scraper_config.type}"')
            return self._empty(provider)
        if not raw_results and transport_failures() and not await internet_reachable():
            raise ProviderUnavailableError('no network connectivity')

        logger.info(provider.id, f'Search "{pieces.query}" on {site.name} → {len(raw_results)} result(s)')

        filename_site = canonical_site_display(parsed.site_token)
        results = []
        for raw in raw_results:
            score = raw.score if raw.score is not None else title_distance_score(pieces.query, raw.title)
            results.append(
                self._mapper.to_match_result(
                    raw,
                    site.name,
                    score,
                    provider.plex_identifier,
                    raw.release_date or None,
                    scraper_type=site.scraper_config.type,
                    filename_site=filename_site,
                )
            )
        results.sort(key=lambda r: r.score or 0, reverse=True)
        deduped = list({r.ratingKey: r for r in results}.values())
        if len(deduped) != len(results):
            logger.info(provider.id, f'dropped {len(results) - len(deduped)} duplicate result(s) sharing a ratingKey')
            results = deduped
        for r in results:
            logger.debug(provider.id, f'result score={r.score} ratingKey={r.ratingKey} "{r.title}"')

        if not is_manual:
            chosen, why = auto_match(results)
            logger.info(provider.id, f'Auto match: {why}')
            if chosen is None:
                return self._empty(provider)
            results = [chosen]

        response = PlexMatchResponse.model_validate(media_container(provider.plex_identifier, results))
        logger.debug(provider.id, f'match response -> {response.model_dump_json(by_alias=True, exclude_none=True)}')
        return response

    def _empty(self, provider: ProviderInfo) -> PlexMatchResponse:
        return PlexMatchResponse.model_validate(empty_media_container(provider.plex_identifier))
