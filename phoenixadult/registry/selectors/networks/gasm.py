from __future__ import annotations

from phoenixadult.registry.selectors._factory import make_site
from phoenixadult.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'GASM'
PROVIDER_BASE_URL = 'https://www.gasm.com'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/search/videos?s='


def _site(name: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=PROVIDER_BASE_URL,
        search_path=PROVIDER_SEARCH_PATH,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='gasm',
    )


GASM_SITES: list[SiteInfo] = [
    _site('GASM'),
    _site('Magma Film'),
    _site('JapanHD'),
    _site('Pure XXX Films'),
    _site('Harmony Vision'),
    _site('Paradise Films'),
    _site('Leche69'),
    _site('Cosplay Babes'),
    _site('Fun Movies'),
    _site('MMV Films'),
    _site('Inflagranti'),
    _site('Hot Gold'),
    _site('The Undercover Lover'),
    _site('Herzog'),
    _site('Butt Formation'),
    _site('PornXN'),
    _site('Filthy and Fisting'),
]
