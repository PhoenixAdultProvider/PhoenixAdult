from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Thick Cash'
PROVIDER_CONTENT_TYPE: ContentType = 'actors'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = 'Actor only, Date Add'
PROVIDER_SEARCH_PATH = '/models/{query}.html'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Family Lust', host='familylust.com'),
    PROVIDER.site('Over 40 Handjobs', host='over40handjobs.com'),
    PROVIDER.site('Ebony Tugs', host='ebonytugs.com'),
    PROVIDER.site('Teen Tugs', host='teentugs.com'),
]
