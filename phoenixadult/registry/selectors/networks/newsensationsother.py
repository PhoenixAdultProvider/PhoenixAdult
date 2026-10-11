from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'New Sensations'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Tales From the Edge', host='thetalesfromtheedge.com', search_path='/tour_ttfte/search.php?query={query}'),
    PROVIDER.site('Fresh Out of High School', host='freshoutofhighschool.com', search_path='/tour_fohs/search.php?query={query}'),
    PROVIDER.site('The Tabu Tales', host='thetabutales.com', search_path='/tour_tt/search.php?query={query}'),
    PROVIDER.site("Shane Diesel's Banging Babes", host='www.shanedieselsbanginbabes.com', search_path='/tour_sdbb/search.php?query={query}'),
    PROVIDER.site('The Romance Series', host='theromanceseries.com', search_path='/tour_rs/search.php?query={query}'),
]
