from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Finishes The Job'
PROVIDER_BASE_URL = 'https://www.finishesthejob.com'
PROVIDER_SEARCH_PATH = '/search?search={query}'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = 'Date Add'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Mano Job'),
    PROVIDER.site('The Dick Suckers'),
    PROVIDER.site('Mister POV'),
]
