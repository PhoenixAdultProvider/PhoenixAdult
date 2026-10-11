from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Allure Media'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = ''

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site(
        'Amateur Allure',
        host='amateurallure.com',
        search_path='/tour/search.php?st=advanced&cat[]=5&qany={query}',
        image_referers=['https://amateurallure.com'],
    ),
    PROVIDER.site(
        'Swallow Salon', host='swallowsalon.com', search_path='/search.php?st=advanced&cat[]=5&qany={query}', image_referers=['https://swallowsalon.com']
    ),
]
