from __future__ import annotations

from app.models.scraper_config import ScraperConfig
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'PKJ Media'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = 'Title only'


def _site(name: str, host: str) -> SiteInfo:
    return SiteInfo(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path='/?s={query}',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_config=ScraperConfig(type='pkjmedia'),
    )


PKJMEDIA_SITES: list[SiteInfo] = [
    _site('My POV Fam', 'www.mypovfam.com'),
    _site('Perverted POV', 'www.pervertedpov.com'),
    _site("Peter's Kingdom", 'peterskingdom.com'),
    _site('Raw White Meat', 'rawwhitemeat.com'),
    _site('Sluts Around Town', 'slutsaroundtown.com'),
]
