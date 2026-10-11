from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'WoodmanCastingX'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = 'actress'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('WoodmanCastingX', host='www.woodmancastingx.com', search_path='/search?query={query}'),
]
