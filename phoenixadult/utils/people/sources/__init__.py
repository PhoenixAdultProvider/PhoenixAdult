from __future__ import annotations

from phoenixadult.config.env import env
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.people.sources.adultDvdEmpire import adult_dvd_empire_source
from phoenixadult.utils.people.sources.babepedia import babepedia_source
from phoenixadult.utils.people.sources.babesAndStars import babes_and_stars_source
from phoenixadult.utils.people.sources.boobpedia import boobpedia_source
from phoenixadult.utils.people.sources.freeones import freeones_source
from phoenixadult.utils.people.sources.iafd import iafd_source
from phoenixadult.utils.people.sources.indexxx import indexxx_source
from phoenixadult.utils.people.sources.javBus import jav_bus_source
from phoenixadult.utils.people.sources.javDatabase import jav_database_source
from phoenixadult.utils.people.sources.localStorage import local_storage_source
from phoenixadult.utils.people.types import Gender, PersonLookupContext, PersonSource, PhotoHit

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
    raw = env.people_source_order_raw
    if not raw:
        return ALL_SOURCES
    ordered = [_BY_NAME[t.strip().lower()] for t in raw.split(',') if t.strip().lower() in _BY_NAME]
    if ordered:
        logger.debug('people', f'Using actor source order: {", ".join(s.name for s in ordered)}')
    return ordered or ALL_SOURCES


SCENE_TOKEN = 'Scene'


def scene_image_pref() -> tuple[bool, bool]:
    """(use_scene, scene_first) for the scene page's own actor image, from PEOPLE_SOURCE_ORDER: unset ->
    (True, True); 'Scene' absent -> (False, False); else scene_first unless a provider precedes 'Scene'."""
    raw = env.people_source_order_raw
    if not raw:
        return True, True
    tokens = [t.strip().lower() for t in raw.split(',') if t.strip()]
    if SCENE_TOKEN.lower() not in tokens:
        return False, False
    scene_idx = tokens.index(SCENE_TOKEN.lower())
    providers = _BY_NAME.keys() - {local_storage_source.name.lower()}
    first_provider_idx = next((i for i, t in enumerate(tokens) if t in providers), len(tokens))
    return True, scene_idx <= first_provider_idx


async def find_photo(actor_name: str, ctx: PersonLookupContext) -> PhotoHit:
    found_gender: Gender = ''
    for source in _configured_order():
        try:
            hit = await source.find(actor_name, ctx)
            if not hit:
                continue
            found_gender = found_gender or hit.gender
            if hit.url:
                logger.info('people', f'{actor_name} -> {source.name}')
                return PhotoHit(url=hit.url, gender=hit.gender or found_gender, source=source.name)
        except Exception as err:  # noqa: BLE001 - one source failing shouldn't abort the chain
            logger.warn('people', f'{source.name} threw for {actor_name}: {err}')
    if found_gender:
        logger.debug('people', f'{actor_name}: no image found, gender={found_gender} (silhouette fallback)')
    else:
        logger.debug('people', f'{actor_name} not found in any source')
    return PhotoHit(url='', gender=found_gender)
