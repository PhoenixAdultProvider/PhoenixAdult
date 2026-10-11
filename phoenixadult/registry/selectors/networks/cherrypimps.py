from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Cherry Pimps'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/search.php?query={query}'
PROVIDER_BASE_URL = 'https://www.cherrypimps.com'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Cherry Pimps'),
    PROVIDER.site('Wild on Cam', base_url='https://www.wildoncam.com'),
    PROVIDER.site('Cherry Spot'),
    PROVIDER.site('Britney Amber'),
    PROVIDER.site('Confessions.XXX'),
    PROVIDER.site('Cucked.XXX'),
    PROVIDER.site('Drilled.XXX'),
    PROVIDER.site('BCM.XXX'),
    PROVIDER.site('Petite.XXX'),
    PROVIDER.site('Family'),
    PROVIDER.site('Busted'),
    PROVIDER.site('Cheese.XXX'),
    PROVIDER.site('Femme'),
    PROVIDER.site('Fresh'),
    PROVIDER.site('Taboo'),
    PROVIDER.site('Bush'),
    PROVIDER.site('Ginger'),
]
