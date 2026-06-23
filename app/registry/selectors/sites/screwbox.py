from __future__ import annotations

from app.models.scraper_config import ScraperConfig
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Screwbox'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = ''

SCREWBOX_SITES: list[SiteInfo] = [
    SiteInfo(
        name=PROVIDER_NAME,
        provider_name=PROVIDER_NAME,
        base_url='https://screwbox.com',
        search_path='/search.php?query={query}',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_config=ScraperConfig(type='screwbox'),
    ),
]
