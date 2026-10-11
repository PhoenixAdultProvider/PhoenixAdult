from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'LittleCaprice'
PROVIDER_BASE_URL = 'https://www.littlecaprice-dreams.com'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/?s={query}'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Little Caprice Dreams'),
    PROVIDER.site('Buttmuse'),
    PROVIDER.site('Caprice Divas'),
    PROVIDER.site('NasstyX'),
    PROVIDER.site('POVDreams'),
    PROVIDER.site('Streetfuck'),
    PROVIDER.site('SuperprivateX'),
    PROVIDER.site('Wecumtoyou'),
    PROVIDER.site('Xpervo'),
]
