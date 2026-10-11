from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Kelly Madison'
PROVIDER_BASE_URL = 'https://www.pornfidelity.com'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = 'Episode ID or URL ID'
PROVIDER_SEARCH_PATH = '/search?q={query}&type=episodes'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('PornFidelity'),
    PROVIDER.site('TeenFidelity'),
    PROVIDER.site('Kelly Madison'),
]
