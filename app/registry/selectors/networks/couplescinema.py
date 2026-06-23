from __future__ import annotations

from app.models.scraper_config import ScraperConfig
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Couples Cinema'
PROVIDER_BASE_URL = 'https://www.couplescinema.com'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = 'Title or Scene ID'
PROVIDER_SEARCH_PATH = '/search/videos?s={query}'


def _site(name: str) -> SiteInfo:
    return SiteInfo(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=PROVIDER_BASE_URL,
        search_path=PROVIDER_SEARCH_PATH,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_config=ScraperConfig(type='couplescinema'),
    )


COUPLESCINEMA_SITES: list[SiteInfo] = [
    _site('Couple Fantasies'),
    _site('Verso Cinema'),
    _site('Sex School'),
    _site('JoyBear'),
    _site('Common Sensual'),
    _site('Gentle Desire'),
    _site('Petra Joy'),
    _site('Madison Young'),
    _site('Light Southern Cinema'),
    _site('Pink and Whit Productions'),
    _site('Signe Baumane'),
    _site('Maria Beatty'),
    _site('Spark Erotic'),
    _site('Foxhouse Films'),
    _site('Mario Ancewicz'),
    _site('Ninja'),
    _site('Morgana Muses'),
    _site('Thousand Faces Films'),
    _site('The Lifestyle'),
]
