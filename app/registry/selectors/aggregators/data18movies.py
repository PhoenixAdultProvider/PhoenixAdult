from __future__ import annotations

from app.models.scraper_config import ScraperConfig
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Data18 Porn Database'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''

DATA18MOVIES_SITES: list[SiteInfo] = [
    SiteInfo(
        name='Data18 Movies',
        provider_name=PROVIDER_NAME,
        base_url='https://data18.com',
        search_path='/sys/live.php?index=&key=',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_config=ScraperConfig(type='data18movies'),
    ),
]
