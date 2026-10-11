from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Puffy Network'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_BASE_URL = 'https://www.puffynetwork.com'
PROVIDER_SEARCH_PATH = '/videos?search={query}'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Wet and Pissy'),
    PROVIDER.site('Wet and Puffy'),
    PROVIDER.site('Simply Anal'),
    PROVIDER.site('We Like to Suck'),
    PROVIDER.site('Euro Babe Facials'),
]
