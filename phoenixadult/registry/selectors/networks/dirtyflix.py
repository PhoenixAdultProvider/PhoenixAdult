from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Dirty Flix'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = 'Title Only and Date Add'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Trick Your GF', host='trickyourgf.com', search_path='/detailedTrailer/'),
    PROVIDER.site('Make Him Cuckold', host='makehimcuckold.com', search_path='/detailed/'),
    PROVIDER.site('She Is Nerdy', host='sheisnerdy.com', search_path='/detailed/'),
    PROVIDER.site('Tricky Agent', host='trickyagent.com', search_path='/detailedTrailer/'),
]
