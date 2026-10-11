from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Data18 Porn Database'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_BASE_URL = 'https://www.data18.com'
PROVIDER_SEARCH_PATH = '/sys/live.php?index=&key='

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [PROVIDER.site('Data18 Scenes'), PROVIDER.site('Data18 Movie Scene')]
