from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site

PROVIDER_NAME = 'New Sensations'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = 'Date Add'


def _site(name: str, host: str, search_path: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'http://www.{host}',
        search_path=search_path,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='newsensations',
    )


NEWSENSATIONS_SITES: list[SiteInfo] = [
    _site('New Sensations', 'newsensations.com', '/tour_ns/'),
    _site('FamilyXXX', 'familyxxx.com', '/tour_famxxx/'),
]
