from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'InterracialPass'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/search.php?query={query}'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Interracial Pass', host='www.interracialpass.com', search_path='/t1/search.php?query={query}'),
    PROVIDER.site('Backroom Casting Couch', host='backroomcastingcouch.com'),
    PROVIDER.site('BBC Surprise', host='bbcsurprise.com'),
    PROVIDER.site('Exploited College Girls', host='exploitedcollegegirls.com'),
    PROVIDER.site('I Kiss Girls', host='www.ikissgirls.com'),
    PROVIDER.site('HushPass', host='hushpass.com', search_path='/t1/search.php?query={query}'),
    PROVIDER.site('Hot MILFs Fuck', host='hotmilfsfuck.com'),
]
