from __future__ import annotations

from app.models.scraper_config import ScraperConfig
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Naughty America Other Sites'
PROVIDER_CONTENT_TYPE: ContentType = 'actors'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = 'Actor only'

TONIGHTSGIRLFRIEND_SITES: list[SiteInfo] = [
    SiteInfo(
        name='Tonights Girlfriend',
        provider_name=PROVIDER_NAME,
        base_url='https://www.tonightsgirlfriend.com',
        search_path='/pornstar/',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_config=ScraperConfig(type='tonightsgirlfriend'),
    ),
]
