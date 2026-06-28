from __future__ import annotations

from app.registry.selectors._factory import make_site
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Thick Cash'
PROVIDER_CONTENT_TYPE: ContentType = 'actors'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = 'Actor only, Date Add'
_SEARCH_PATH = '/models/{query}.html'


def _site(name: str, host: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path=_SEARCH_PATH,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='thickcash',
    )


THICKCASH_SITES: list[SiteInfo] = [
    _site('Family Lust', 'familylust.com'),
    _site('Over 40 Handjobs', 'over40handjobs.com'),
    _site('Ebony Tugs', 'ebonytugs.com'),
    _site('Teen Tugs', 'teentugs.com'),
]
