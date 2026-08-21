from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site

PROVIDER_NAME = 'Czech VR'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/searching?search={query}'


def _site(name: str, host: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path=PROVIDER_SEARCH_PATH,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='czechvr',
    )


SITES: list[SiteInfo] = [
    _site('Czech VR', 'czechvr.com'),
    _site('Czech VR Fetish', 'czechvrfetish.com'),
    _site('Czech VR Casting', 'czechvrcasting.com'),
    _site('Czech VR Network', 'czechvrnetwork.com'),
    _site('VR Intimacy', 'vrintimacy.com'),
    _site('Czech AR', 'czechar.com'),
]
