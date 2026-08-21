from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site

PROVIDER_NAME = 'Femdom Empire'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/tour/search.php?st=advanced&qany={query}'


def _site(name: str, host: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path=PROVIDER_SEARCH_PATH,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='femdomempire',
    )


SITES: list[SiteInfo] = [
    _site('Femdom Empire', 'femdomempire.com'),
    _site('Feminized', 'feminized.com'),
]
