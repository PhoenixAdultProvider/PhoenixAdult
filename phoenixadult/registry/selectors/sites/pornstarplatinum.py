from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Pornstar Platinum'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Pornstar Platinum', host='www.pornstarplatinum.com', search_path='/tour/index.php?search={query}'),
]
