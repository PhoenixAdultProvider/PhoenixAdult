from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site

PROVIDER_NAME = 'Ultrafilms'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = ''

SITES: list[SiteInfo] = [
    make_site(
        name=PROVIDER_NAME,
        provider_name=PROVIDER_NAME,
        base_url='https://www.ultrafilms.xxx',
        search_path='/?s={query}',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='ultrafilms',
    ),
]
