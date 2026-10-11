from __future__ import annotations

from phoenixadult.models.site_info import BypassName, ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Bellesa'
PROVIDER_BASE_URL = 'https://bellesaplus.co'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_BYPASS: list[BypassName] = ['Impersonate']
PROVIDER_IMAGE_REFERERS = ['https://bellesaplus.co']
PROVIDER_SEARCH_PATH = ''

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Bellesa Films'),
    PROVIDER.site('Bellesa House'),
]
