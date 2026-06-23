from __future__ import annotations

from app.models.scraper_config import ScraperConfig
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Perfect Gonzo'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''

_PG = 'www.perfectgonzo.com'


def _site(name: str, host: str, search_path: str) -> SiteInfo:
    return SiteInfo(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path=search_path,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_config=ScraperConfig(type='perfectgonzo'),
    )


PERFECTGONZO_SITES: list[SiteInfo] = [
    _site('PerfectGonzo', _PG, '/movies?q={query}'),
    _site('All Internal', _PG, '/movies?tag=allinternal&q={query}'),
    _site('Ass Traffic', _PG, '/movies?tag=asstraffic&q={query}'),
    _site('Cum For Cover', _PG, '/movies?tag=cumforcover&q={query}'),
    _site('Give Me Pink', 'givemepink.com', '/movies?tag=givemepink&q={query}'),
    _site('Primecups', _PG, '/movies?tag=primecups&q={query}'),
    _site('PurePOV', _PG, '/movies?tag=purepov&q={query}'),
    _site('Sperm Swap', _PG, '/movies?tag=spermaswap&q={query}'),
    _site('Tamed Teens', _PG, '/movies?tag=tamedteens&q={query}'),
    _site('Fist Flush', _PG, '/movies?tag=fistflush&q={query}'),
    _site('Milf Thing', _PG, '/movies?tag=milfthing&q={query}'),
    _site('Perfect Gonzo Interview', _PG, '/movies?tag=interview&q={query}'),
    _site('SapphiX', 'sapphix.com', '/movies?q={query}'),
    _site('Sapphic Erotica', 'sapphix.com', '/movies?site[]=se&q={query}'),
]
