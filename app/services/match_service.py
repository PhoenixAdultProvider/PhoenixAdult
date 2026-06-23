from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

from app.clients.base import SearchContext
from app.config.env import env
from app.mappers.metadata_mapper import MetadataMapper
from app.models.metadata import PlexMatchResponse
from app.models.provider_info import ProviderInfo
from app.registry import find_site
from app.routes.scraper_router import ScraperRouter
from app.utils.helpers.helpers import format_duration
from app.utils.logging.logger import logger
from app.utils.processors.filename_parser import get_site_name_from_registry
from app.utils.processors.search_query import build_search_pieces
from app.utils.processors.similarity import compare_string


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


class MatchService:
    def __init__(self) -> None:
        self._scraper = ScraperRouter()
        self._mapper = MetadataMapper()

    async def match(self, req: MatchRequest, provider: ProviderInfo, language: str | None = None) -> PlexMatchResponse:
        is_manual = req.manual == 1
        include_adult = req.includeAdult == 1

        logger.info(provider.id, 'Match', title=req.title, filename=req.filename)

        parse_source = req.filename or req.title

        if not include_adult or not parse_source or (env.disable_auto_match and not is_manual):
            logger.info(
                provider.id,
                f'match suppressed (DISABLE_AUTO_MATCH={env.disable_auto_match_raw}, manual={is_manual}, '
                f'includeAdult={include_adult}, parseSource={bool(parse_source)})',
            )
            return self._empty(provider)

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

        raw_results = await self._scraper.search(search_data)
        if raw_results is None:
            logger.warn(provider.id, f'No scraper registered for type "{site.scraper_config.type}"')
            return self._empty(provider)

        logger.info(provider.id, f'Search "{pieces.query}" on {site.name} → {len(raw_results)} result(s)')

        results = []
        for raw in raw_results:
            score = raw.score if raw.score is not None else 80 - compare_string(pieces.query, raw.title).levenshtein
            results.append(
                self._mapper.to_match_result(raw, site.name, score, provider.plex_identifier, raw.release_date or None, scraper_type=site.scraper_config.type)
            )
        results.sort(key=lambda r: r.score or 0, reverse=True)

        return PlexMatchResponse.model_validate(
            {
                'MediaContainer': {
                    'offset': 0,
                    'totalSize': len(results),
                    'identifier': provider.plex_identifier,
                    'size': len(results),
                    'Metadata': results,
                }
            }
        )

    def _empty(self, provider: ProviderInfo) -> PlexMatchResponse:
        return PlexMatchResponse.model_validate(
            {
                'MediaContainer': {
                    'offset': 0,
                    'totalSize': 0,
                    'identifier': provider.plex_identifier,
                    'size': 0,
                    'Metadata': [],
                }
            }
        )
