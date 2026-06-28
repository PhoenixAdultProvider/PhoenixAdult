from __future__ import annotations

from app.registry.selectors._factory import make_site
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'High-Tech VR'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'exact'
PROVIDER_SEARCH_NOTES = 'Direct URL'

XSINSVR_SITES: list[SiteInfo] = [
    make_site(
        name='SinsVR',
        provider_name=PROVIDER_NAME,
        base_url='https://www.xsinsvr.com',
        search_path='/search/',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='xsinsvr',
    ),
]
