from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Jules Jordan'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = 'Movies Not Supported'
PROVIDER_SEARCH_PATH = '/trial/search.php?query={query}'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Jules Jordan', host='www.julesjordan.com'),
    PROVIDER.site('Manuel Ferrara', host='www.manuelferrara.com'),
    PROVIDER.site('The Ass Factory', host='www.theassfactory.com'),
    PROVIDER.site('Sperm Swallowers', host='www.spermswallowers.com'),
    PROVIDER.site('GirlGirl', host='www.girlgirl.com'),
]
