from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'SinX'
PROVIDER_BASE_URL = 'https://sinx.com'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/videos/all?sexualOrientation=0&searchWord={query}'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Pissing in Action'),
    PROVIDER.site('Golden Shower Power'),
    PROVIDER.site('Fully Clothed Pissing'),
    PROVIDER.site('Slime Wave'),
]
