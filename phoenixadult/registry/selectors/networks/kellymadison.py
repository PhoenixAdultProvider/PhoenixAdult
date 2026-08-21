from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site

PROVIDER_NAME = 'Kelly Madison'
PROVIDER_BASE_URL = 'https://www.pornfidelity.com'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = 'Episode ID or URL ID'
PROVIDER_SEARCH_PATH = '/search?q={query}&type=episodes'


def _site(name: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=PROVIDER_BASE_URL,
        search_path=PROVIDER_SEARCH_PATH,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='kellymadison',
    )


SITES: list[SiteInfo] = [
    _site('PornFidelity'),
    _site('TeenFidelity'),
    _site('Kelly Madison'),
]
