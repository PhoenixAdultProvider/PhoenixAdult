from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Caramel Cash'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'exact'
PROVIDER_SEARCH_NOTES = 'Scene ID'
PROVIDER_SEARCH_PATH = '/video/{query}'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('VR PMV Bay', host='vrpmvbay.com'),
    PROVIDER.site('Cuckold Wish', host='cuckoldwish.com', search_path='/videos/{query}'),
    PROVIDER.site('Alex Legend', host='alexlegend.com'),
]
