from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'FuelVirtual'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('FuckedHard18', host='fuckedhard18.com', search_path='/membersarea/search.php?st=advanced&site[]=5&qall='),
    PROVIDER.site('MassageGirls18', host='massagegirls18.com', search_path='/membersarea/search.php?st=advanced&site[]=4&qall='),
    PROVIDER.site('NewGirlPOV', host='pornmastermind.com', search_path='/tour/newgirlpov/search.php?qall='),
]
