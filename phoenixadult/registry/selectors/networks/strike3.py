from __future__ import annotations

from phoenixadult.models.site_info import BypassName, ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Strike3'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_BYPASS: list[BypassName] = ['Impersonate']
PROVIDER_DATA18_ENRICHMENT = True
PROVIDER_SCENE_TEMPLATE = '{base}/videos/{head}'
PROVIDER_SEARCH_PATH = ''

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Blacked', host='www.blacked.com'),
    PROVIDER.site('Blacked RAW', host='www.blackedraw.com'),
    PROVIDER.site('Vixen', host='www.vixen.com'),
    PROVIDER.site('Tushy', host='www.tushy.com'),
    PROVIDER.site('Tushy RAW', host='www.tushyraw.com'),
    PROVIDER.site('Deeper', host='www.deeper.com'),
    PROVIDER.site('Slayed', host='www.slayed.com'),
    PROVIDER.site('Milfy', host='www.milfy.com'),
    PROVIDER.site('Wifey', host='www.wifey.com'),
]
