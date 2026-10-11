from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'GASM'
PROVIDER_BASE_URL = 'https://www.gasm.com'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/search/videos?s='

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('GASM'),
    PROVIDER.site('Magma Film'),
    PROVIDER.site('JapanHD'),
    PROVIDER.site('Pure XXX Films'),
    PROVIDER.site('Harmony Vision'),
    PROVIDER.site('Paradise Films'),
    PROVIDER.site('Leche69'),
    PROVIDER.site('Cosplay Babes'),
    PROVIDER.site('Fun Movies'),
    PROVIDER.site('MMV Films'),
    PROVIDER.site('Inflagranti'),
    PROVIDER.site('Hot Gold'),
    PROVIDER.site('The Undercover Lover'),
    PROVIDER.site('Herzog'),
    PROVIDER.site('Butt Formation'),
    PROVIDER.site('PornXN'),
    PROVIDER.site('Filthy and Fisting'),
]
