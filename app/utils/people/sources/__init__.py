from __future__ import annotations

from app.config.env import env
from app.utils.logging.logger import logger
from app.utils.people.sources.adultDvdEmpire import adult_dvd_empire_source
from app.utils.people.sources.babepedia import babepedia_source
from app.utils.people.sources.babesAndStars import babes_and_stars_source
from app.utils.people.sources.boobpedia import boobpedia_source
from app.utils.people.sources.freeones import freeones_source
from app.utils.people.sources.iafd import iafd_source
from app.utils.people.sources.indexxx import indexxx_source
from app.utils.people.sources.javBus import jav_bus_source
from app.utils.people.sources.javDatabase import jav_database_source
from app.utils.people.sources.localStorage import local_storage_source
from app.utils.people.types import PersonLookupContext, PersonSource, PhotoHit

ALL_SOURCES: list[PersonSource] = [
    local_storage_source,
    freeones_source,
    iafd_source,
    indexxx_source,
    adult_dvd_empire_source,
    boobpedia_source,
    babes_and_stars_source,
    babepedia_source,
    jav_bus_source,
    jav_database_source,
]

_BY_NAME = {s.name.lower(): s for s in ALL_SOURCES}


def _configured_order() -> list[PersonSource]:
    raw = env.actor_source_order_raw
    if not raw:
        return ALL_SOURCES
    ordered = [_BY_NAME[t.strip().lower()] for t in raw.split(',') if t.strip().lower() in _BY_NAME]
    if ordered:
        logger.debug('people', f'Using actor source order: {", ".join(s.name for s in ordered)}')
    return ordered or ALL_SOURCES


async def find_photo(actor_name: str, ctx: PersonLookupContext) -> PhotoHit:
    for source in _configured_order():
        try:
            hit = await source.find(actor_name, ctx)
            if hit and hit.url:
                logger.info('people', f'{actor_name} -> {source.name}')
                return PhotoHit(url=hit.url, gender=hit.gender or '')
        except Exception as err:  # noqa: BLE001 - one source failing shouldn't abort the chain
            logger.warn('people', f'{source.name} threw for {actor_name}: {err}')
    logger.debug('people', f'{actor_name} not found in any source')
    return PhotoHit(url='', gender='')
