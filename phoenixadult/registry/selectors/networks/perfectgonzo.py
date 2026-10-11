from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Perfect Gonzo'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''

_PG = 'www.perfectgonzo.com'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('PerfectGonzo', host=_PG, search_path='/movies?q={query}'),
    PROVIDER.site('All Internal', host=_PG, search_path='/movies?tag=allinternal&q={query}'),
    PROVIDER.site('Ass Traffic', host=_PG, search_path='/movies?tag=asstraffic&q={query}'),
    PROVIDER.site('Cum for Cover', host=_PG, search_path='/movies?tag=cumforcover&q={query}'),
    PROVIDER.site('Give Me Pink', host='givemepink.com', search_path='/movies?tag=givemepink&q={query}'),
    PROVIDER.site('Primecups', host=_PG, search_path='/movies?tag=primecups&q={query}'),
    PROVIDER.site('PurePOV', host=_PG, search_path='/movies?tag=purepov&q={query}'),
    PROVIDER.site('Sperm Swap', host=_PG, search_path='/movies?tag=spermaswap&q={query}'),
    PROVIDER.site('Tamed Teens', host=_PG, search_path='/movies?tag=tamedteens&q={query}'),
    PROVIDER.site('Fist Flush', host=_PG, search_path='/movies?tag=fistflush&q={query}'),
    PROVIDER.site('MILF Thing', host=_PG, search_path='/movies?tag=milfthing&q={query}'),
    PROVIDER.site('Perfect Gonzo Interview', host=_PG, search_path='/movies?tag=interview&q={query}'),
    PROVIDER.site('SapphiX', host='sapphix.com', search_path='/movies?q={query}'),
    PROVIDER.site('Sapphic Erotica', host='sapphix.com', search_path='/movies?site[]=se&q={query}'),
]
