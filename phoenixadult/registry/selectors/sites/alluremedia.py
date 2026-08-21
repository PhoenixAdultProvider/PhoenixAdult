from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site

PROVIDER_NAME = 'Allure Media'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = ''


def _site(name: str, host: str, search_path: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path=search_path,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='alluremedia',
        image_referers=[f'https://{host}'],
    )


SITES: list[SiteInfo] = [
    _site('Amateur Allure', 'amateurallure.com', '/tour/search.php?st=advanced&cat[]=5&qany={query}'),
    _site('Swallow Salon', 'swallowsalon.com', '/search.php?st=advanced&cat[]=5&qany={query}'),
]
