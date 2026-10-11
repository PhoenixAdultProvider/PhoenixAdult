from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'New Sensations'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = 'Date Add'
PROVIDER_BASE_URL = 'http://www.{host}'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('New Sensations', host='newsensations.com', search_path='/tour_ns/'),
    PROVIDER.site('FamilyXXX', host='familyxxx.com', search_path='/tour_famxxx/'),
]
