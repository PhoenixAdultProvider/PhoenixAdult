from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Stepped Up Media'
PROVIDER_CONTENT_TYPE: ContentType = 'actors'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = 'Actor only'
PROVIDER_SCENE_TEMPLATE = '{base}/scenes/{head}'
PROVIDER_SEARCH_PATH = ''

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Swallowed', host='tour.swallowed.com'),
    PROVIDER.site('True Anal', host='tour.trueanal.com'),
    PROVIDER.site('Nympho', host='tour.nympho.com'),
    PROVIDER.site('All Anal', host='tour.allanal.com'),
    PROVIDER.site('Anal Only', host='tour.analonly.com'),
    PROVIDER.site('Dirty Auditions', host='dirtyauditions.com'),
]
