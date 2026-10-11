from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Killergram'
PROVIDER_BASE_URL = 'https://killergram.com'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneId'
PROVIDER_SEARCH_METHOD: SearchMethod = 'exact'
PROVIDER_SEARCH_NOTES = 'SceneID'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Killergram', search_path='/episodes.asp?page=episodes&id={query}'),
    PROVIDER.site('Killergram Platinum', search_path='/platinum.asp?page=platinum&id={query}'),
]
