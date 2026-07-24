from __future__ import annotations

from phoenixadult.registry.selectors._factory import make_site
from phoenixadult.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'SinX'
PROVIDER_BASE_URL = 'https://sinx.com'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = ''
_SEARCH_PATH = '/videos/all?sexualOrientation=0&searchWord={query}'


def _site(name: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=PROVIDER_BASE_URL,
        search_path=_SEARCH_PATH,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='sinx',
    )


SINX_SITES: list[SiteInfo] = [
    _site('Pissing In Action'),
    _site('Golden Shower Power'),
    _site('Fully Clothed Pissing'),
    _site('Slime Wave'),
]
