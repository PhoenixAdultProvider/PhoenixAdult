from __future__ import annotations

from app.models.scraper_config import ScraperConfig
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Caramel Cash'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'exact'
PROVIDER_SEARCH_NOTES = 'Scene ID'


def _site(name: str, host: str, search_path: str) -> SiteInfo:
    return SiteInfo(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path=f'{search_path}/{{query}}',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_config=ScraperConfig(type='caramelcash'),
    )


CARAMELCASH_SITES: list[SiteInfo] = [
    _site('VrpmvBay', 'vrpmvbay.com', '/video'),
    _site('CuckoldWish', 'cuckoldwish.com', '/videos'),
    _site('Alex Legend', 'alexlegend.com', '/video'),
]
