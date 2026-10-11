from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Blurred Media'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/videos/search?s={query}'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Sugar Daddy Porn', host='sugardaddyporn.com'),
    PROVIDER.site('Hot Guys Fuck', host='hotguysfuck.com'),
    PROVIDER.site('Bi Guys Fuck', host='biguysfuck.com'),
    PROVIDER.site('Gay Hoopla', host='gayhoopla.com'),
]
