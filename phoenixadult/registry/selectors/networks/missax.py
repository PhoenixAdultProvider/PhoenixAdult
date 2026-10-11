from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'MissaX'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/search.php?query={query}'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('MissaX', base_url='https://missax.com', search_path='/tour/search.php?query={query}'),
    PROVIDER.site('AllHerLuv', base_url='https://allherluv.com', search_path='/tour/search.php?query={query}'),
    PROVIDER.site('Exposed Whores', base_url='https://exposedwhores.com/new-tour'),
    PROVIDER.site('She Seduced Me', base_url='https://www.sheseducedme.com'),
    PROVIDER.site('House of Fyre', base_url='https://www.houseofyre.com'),
    PROVIDER.site('Philavise', base_url='https://www.philavise.com'),
    PROVIDER.site('Lauren Phillips', base_url='https://laurenphillips.com'),
]
