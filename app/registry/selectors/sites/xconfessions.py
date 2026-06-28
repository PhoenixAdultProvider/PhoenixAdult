from __future__ import annotations

from app.registry.selectors._factory import make_site
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'XConfessions'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = ''


def _xconf(name: str, base_url: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=base_url,
        search_path='/api/search',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='xconfessions',
    )


XCONFESSIONS_SITES: list[SiteInfo] = [
    _xconf('XConfessions', 'https://api.xconfessions.com'),
    _xconf('LustCinema', 'https://next-prod-api.lustcinema.com'),
]
