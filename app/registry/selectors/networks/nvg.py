from __future__ import annotations

from app.models.scraper_config import ScraperConfig
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'NVG Network'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'exact'
PROVIDER_SEARCH_NOTES = 'SceneID Only, Date Add, Actor Add (Name1 AND Name2)'


NVG_SITES: list[SiteInfo] = [
    SiteInfo(
        name='Net Video Girls',
        provider_name=PROVIDER_NAME,
        base_url='https://netvideogirls.net',
        search_path='',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_config=ScraperConfig(type='nvg'),
    ),
]
