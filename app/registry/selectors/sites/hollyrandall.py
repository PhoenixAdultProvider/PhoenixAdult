from __future__ import annotations

from app.registry.selectors._factory import make_site
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Holly Randall'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = ''

HOLLYRANDALL_SITES: list[SiteInfo] = [
    make_site(
        name=PROVIDER_NAME,
        provider_name='Holly Randall Productions',
        base_url='https://hollyrandall.com',
        search_path='/search.php?query={query}',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='hollyrandall',
    ),
]
