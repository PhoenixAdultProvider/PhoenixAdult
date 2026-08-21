from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site

PROVIDER_NAME = 'ALS Angels'
PROVIDER_CONTENT_TYPE: ContentType = 'actors'
PROVIDER_SEARCH_METHOD: SearchMethod = 'exact'
PROVIDER_SEARCH_NOTES = 'Actress name with subject, Date Add'

SITES: list[SiteInfo] = [
    make_site(
        name=PROVIDER_NAME,
        provider_name=PROVIDER_NAME,
        base_url='https://alsangels.com',
        search_path='',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='alsangels',
    ),
]
