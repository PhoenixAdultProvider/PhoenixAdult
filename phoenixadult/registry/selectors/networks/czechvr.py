from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Czech VR'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/searching?search={query}'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Czech VR', host='czechvr.com'),
    PROVIDER.site('Czech VR Fetish', host='czechvrfetish.com'),
    PROVIDER.site('Czech VR Casting', host='czechvrcasting.com'),
    PROVIDER.site('Czech VR Network', host='czechvrnetwork.com'),
    PROVIDER.site('VR Intimacy', host='vrintimacy.com'),
    PROVIDER.site('Czech AR', host='czechar.com'),
]
