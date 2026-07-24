from __future__ import annotations

from typing import TYPE_CHECKING

from phoenixadult.utils.logging.logger import logger

if TYPE_CHECKING:
    from phoenixadult.clients.base import SceneDetail


def log_search_data(
    provider_id: str,
    *,
    source: str,
    query: str,
    site_name: str,
    scraper_type: str,
    date: str | None = None,
    filename: str | None = None,
) -> None:
    logger.info(provider_id, f'***MEDIA TITLE*** "{source}"')
    logger.info(provider_id, f'SearchData.title: {query}')
    if date:
        logger.info(provider_id, f'SearchData.date: {date}')
    if filename:
        logger.info(provider_id, f'SearchData.filename: {filename}')
    logger.info(provider_id, f'Provider: {scraper_type} -> {site_name}')


def log_search_count(provider_id: str, site_name: str, query: str, count: int) -> None:
    logger.info(provider_id, f'{site_name} search "{query}" -> {count} result(s)')


def log_update_header(provider_id: str, rating_key: str) -> None:
    logger.info(provider_id, f'getMetadata ratingKey={rating_key}')
    logger.info(provider_id, '******UPDATE CALLED*******')


def log_update_provider(provider_id: str, site_name: str, scraper_type: str) -> None:
    logger.info(provider_id, f'Site: {site_name}')
    logger.info(provider_id, f'Provider: {scraper_type}')


def log_detail_summary(provider_id: str, site_name: str, detail: SceneDetail) -> None:
    logger.info(
        provider_id,
        f'{site_name} detail "{detail.title}" -> '
        f'{len(detail.collections or [])} collection(s), {len(detail.genres)} genre(s), '
        f'{len(detail.actors)} actor(s), {len(detail.directors or [])} director(s), '
        f'{len(detail.producers or [])} producer(s), {len(detail.art)} image(s)',
    )
