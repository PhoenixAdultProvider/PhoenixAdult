from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'PKJ Media'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = 'Title only'
PROVIDER_SEARCH_PATH = '/?s={query}'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('My POV Fam', host='www.mypovfam.com'),
    PROVIDER.site('Perverted POV', host='www.pervertedpov.com'),
    PROVIDER.site("Peter's Kingdom", host='peterskingdom.com'),
    PROVIDER.site('Raw White Meat', host='rawwhitemeat.com'),
    PROVIDER.site('Sluts Around Town', host='slutsaroundtown.com'),
]
