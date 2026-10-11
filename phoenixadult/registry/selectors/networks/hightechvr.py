from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'High-Tech VR'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'exact'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('SexBabesVR', host='sexbabesvr.com', search_path='/video/{query}', search_notes='Direct URL'),
    PROVIDER.site('StasyQ VR', host='stasyqvr.com', search_path='/virtualreality/scene/id/{query}', search_notes='SceneID'),
    PROVIDER.site('RealJamVR', host='realjamvr.com', search_path='/scene/{query}', search_notes='Direct URL'),
]
