from __future__ import annotations

from app.registry.selectors._factory import make_site
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Bel Ami Online'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneId'
PROVIDER_SEARCH_METHOD: SearchMethod = 'exact'
PROVIDER_SEARCH_NOTES = 'SceneID'

BELAMI_SITES: list[SiteInfo] = [
    make_site(
        name=PROVIDER_NAME,
        provider_name=PROVIDER_NAME,
        base_url='https://newtour.belamionline.com',
        search_path='/playvideo.aspx?VideoID={query}',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='belami',
    ),
]
