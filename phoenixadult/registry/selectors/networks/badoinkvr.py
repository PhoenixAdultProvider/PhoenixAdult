from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'BaDoink VR'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_DATA18_ENRICHMENT = True
PROVIDER_SEARCH_PATH = '/vrpornvideos/search/{query}'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('BaDoink VR', host='badoinkvr.com'),
    PROVIDER.site('Babe VR', host='babevr.com'),
    PROVIDER.site('18 VR', host='18vr.com'),
    PROVIDER.site('VRCosplayX', host='vrcosplayx.com', search_path='/cosplaypornvideos/search/{query}'),
    PROVIDER.site('Passthrough VR', host='realvr.com'),
]
