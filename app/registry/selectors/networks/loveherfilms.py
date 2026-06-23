from __future__ import annotations

from app.models.scraper_config import ScraperConfig
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'LoveHerFilms'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/tour/search.php?query={query}'


def _site(name: str, host: str) -> SiteInfo:
    return SiteInfo(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path=PROVIDER_SEARCH_PATH,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_config=ScraperConfig(type='loveherfilms'),
    )


LOVEHERFILMS_SITES: list[SiteInfo] = [
    _site('LoveHerFilms', 'www.loveherfilms.com'),
    _site('LoveHerBoobs', 'www.loveherboobs.com'),
    _site('LoveHerFeet', 'www.loveherfeet.com'),
    _site('SheLovesBlack', 'www.shelovesblack.com'),
]
