from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site

PROVIDER_NAME = 'TwoTGirls'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = 'Title only'

SITES: list[SiteInfo] = [
    make_site(
        name=PROVIDER_NAME,
        provider_name=PROVIDER_NAME,
        base_url='https://twotgirls.com',
        search_path='/videos?query={query}',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='twotgirls',
    ),
]
