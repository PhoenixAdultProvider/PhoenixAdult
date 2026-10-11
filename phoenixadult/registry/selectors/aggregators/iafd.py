from __future__ import annotations

from phoenixadult.models.site_info import BypassName, ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'IAFD'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_BYPASS: list[BypassName] = ['Impersonate']
PROVIDER_BASE_URL = 'https://www.iafd.com'
PROVIDER_SCENE_TEMPLATE = f'{PROVIDER_BASE_URL}/title.rme/id={{head}}'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Black Patrol', search_path='/distrib.rme/distrib=9954/blackpatrol.com.htm'),
]
