from __future__ import annotations

from phoenixadult.registry.selectors._factory import make_site
from phoenixadult.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'In the Crack'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneIdName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = 'Actor only'

INTHECRACK_SITES: list[SiteInfo] = [
    make_site(
        name=PROVIDER_NAME,
        provider_name='InTheCrack',
        base_url='https://inthecrack.com',
        search_path='/Collections/Name/',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='inthecrack',
    ),
]
