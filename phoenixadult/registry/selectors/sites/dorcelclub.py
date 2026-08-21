from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site

PROVIDER_NAME = 'Dorcel Club'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''

DORCELCLUB_SITES: list[SiteInfo] = [
    make_site(
        name=PROVIDER_NAME,
        provider_name='Marc Dorcel',
        base_url='https://www.dorcelclub.com',
        search_path='/en/search?s={query}',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='dorcelclub',
    ),
]
