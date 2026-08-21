from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site

PROVIDER_NAME = 'Puffy Network'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = ''
_BASE_URL = 'https://www.puffynetwork.com'


def _site(name: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=_BASE_URL,
        search_path='/videos?search={query}',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='puffy',
    )


SITES: list[SiteInfo] = [
    _site('Wet and Pissy'),
    _site('Wet and Puffy'),
    _site('Simply Anal'),
    _site('We Like to Suck'),
    _site('Euro Babe Facials'),
]
