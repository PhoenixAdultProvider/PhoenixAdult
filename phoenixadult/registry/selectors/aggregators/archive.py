from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site
from phoenixadult.utils.helpers.helpers import load_data

PROVIDER_NAME = 'Archive'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = 'Cached Scenes Only — Site Retired'

ARCHIVE_SITES: list[SiteInfo] = [
    make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url='',
        search_path='',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='archive',
    )
    for name in load_data(__file__, 'archive_sites')
]
