from __future__ import annotations

from app.models.scraper_config import ScraperConfig
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'ReidMyLips'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'exact'
PROVIDER_SEARCH_NOTES = 'Direct URL'

REIDMYLIPS_SITES: list[SiteInfo] = [
    SiteInfo(
        name=PROVIDER_NAME,
        provider_name=PROVIDER_NAME,
        base_url='https://www.reidmylips.com',
        search_path='/updates/',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_config=ScraperConfig(type='reidmylips'),
    ),
]
