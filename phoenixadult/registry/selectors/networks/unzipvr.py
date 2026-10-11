from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Unzip VR'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = ''

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('VR Bangers', host='content.vrbangers.com', data18_enrichment=True),
    PROVIDER.site('VR Conk', host='content.vrconk.com', data18_enrichment=True),
    PROVIDER.site('Blow VR', host='content.blowvr.com'),
    PROVIDER.site('VRB Trans', host='content.vrbtrans.com'),
    PROVIDER.site('VRB Gay', host='content.vrbgay.com'),
]
