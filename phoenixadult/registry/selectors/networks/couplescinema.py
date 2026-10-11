from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Couples Cinema'
PROVIDER_BASE_URL = 'https://www.couplescinema.com'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = 'Title or Scene ID'
PROVIDER_SEARCH_PATH = '/search/videos?s={query}'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Couple Fantasies'),
    PROVIDER.site('Verso Cinema'),
    PROVIDER.site('Sex School'),
    PROVIDER.site('JoyBear'),
    PROVIDER.site('Common Sensual'),
    PROVIDER.site('Gentle Desire'),
    PROVIDER.site('Petra Joy'),
    PROVIDER.site('Madison Young'),
    PROVIDER.site('Light Southern Cinema'),
    PROVIDER.site('Pink and Whit Productions'),
    PROVIDER.site('Signe Baumane'),
    PROVIDER.site('Maria Beatty'),
    PROVIDER.site('Spark Erotic'),
    PROVIDER.site('Foxhouse Films'),
    PROVIDER.site('Mario Ancewicz'),
    PROVIDER.site('Ninja'),
    PROVIDER.site('Morgana Muses'),
    PROVIDER.site('Thousand Faces Films'),
    PROVIDER.site('The Lifestyle'),
]
