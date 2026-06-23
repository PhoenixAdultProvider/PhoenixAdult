from __future__ import annotations

from app.models.scraper_config import ScraperConfig
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'New Sensations'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''


def _site(name: str, host: str, search_path: str) -> SiteInfo:
    return SiteInfo(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path=search_path,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_config=ScraperConfig(type='newsensationsother'),
    )


NEWSENSATIONSOTHER_SITES: list[SiteInfo] = [
    _site('Tales From the Edge', 'thetalesfromtheedge.com', '/tour_ttfte/search.php?query={query}'),
    _site('Fresh Out Of High School', 'freshoutofhighschool.com', '/tour_fohs/search.php?query={query}'),
    _site('The Tabu Tales', 'thetabutales.com', '/tour_tt/search.php?query={query}'),
    _site("Shane Diesel's Banging Babes", 'www.shanedieselsbanginbabes.com', '/tour_sdbb/search.php?query={query}'),
    _site('The Romance Series', 'theromanceseries.com', '/tour_rs/search.php?query={query}'),
]
