from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site

PROVIDER_NAME = 'Gamma'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''


def _site(name: str, host: str, studio: str, search_path: str = '/en/search/scene/') -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        sub_group=studio,
        base_url=f'http://www.{host}',
        search_path=search_path,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='gammaent',
    )


SITES: list[SiteInfo] = [
    _site('Tera Patrick', 'terapatrick.com', 'Fame Digital', '/en/search/'),
    _site('Sunny Leone', 'sunnyleone.com', 'Open Life Network'),
    _site('Lane Sisters', 'lanesisters.com', 'Open Life Network'),
    _site('Dylan Ryder', 'dylanryder.com', 'Open Life Network'),
    _site('Abbey Brooks', 'abbeybrooks.com', 'Open Life Network'),
    _site('Devon Lee', 'devonlee.com', 'Open Life Network'),
    _site('Hanna Hilton', 'hannahilton.com', 'Open Life Network'),
]
