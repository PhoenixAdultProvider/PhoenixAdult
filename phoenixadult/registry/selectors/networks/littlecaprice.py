from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site

PROVIDER_NAME = 'LittleCaprice'
PROVIDER_BASE_URL = 'https://www.littlecaprice-dreams.com'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/?s={query}'


def _site(name: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=PROVIDER_BASE_URL,
        search_path=PROVIDER_SEARCH_PATH,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='littlecaprice',
    )


LITTLECAPRICE_SITES: list[SiteInfo] = [
    _site('Little Caprice Dreams'),
    _site('Buttmuse'),
    _site('Caprice Divas'),
    _site('NasstyX'),
    _site('POVDreams'),
    _site('Streetfuck'),
    _site('SuperprivateX'),
    _site('Wecumtoyou'),
    _site('Xpervo'),
]
