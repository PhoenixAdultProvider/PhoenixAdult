from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Karups'
PROVIDER_BASE_URL = 'https://www.karups.com'
PROVIDER_CONTENT_TYPE: ContentType = 'actors'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = 'Actor only'
PROVIDER_SEARCH_PATH = '/models/search/'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('KarupsPC'),
    PROVIDER.site('KarupsHA'),
    PROVIDER.site('KarupsOW'),
]
