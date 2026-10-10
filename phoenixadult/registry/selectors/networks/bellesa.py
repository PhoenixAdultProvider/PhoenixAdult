from __future__ import annotations

from phoenixadult.models.site_info import BypassName, ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site

PROVIDER_NAME = 'Bellesa'
PROVIDER_BASE_URL = 'https://bellesaplus.co'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_BYPASS: list[BypassName] = ['Impersonate']


def _site(name: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=PROVIDER_BASE_URL,
        search_path='',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        bypass=PROVIDER_BYPASS,
        scraper_type='bellesa',
        image_referers=[PROVIDER_BASE_URL],
    )


SITES: list[SiteInfo] = [
    _site('Bellesa Films'),
    _site('Bellesa House'),
]
