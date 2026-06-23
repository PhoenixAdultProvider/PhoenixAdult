from __future__ import annotations

from app.models.scraper_config import ScraperConfig
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Private'
PROVIDER_BASE_URL = 'https://www.private.com'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/search.php?query={query}'

_NAMES = [
    'Private',
    'Anal Introductions',
    'Blacks on Sluts',
    'I Confess Files',
    'Private Fetish',
    'Mission Ass Possible',
    'Private MILFs',
    'Russian Fake Agent',
    'Russian Teen Ass',
    'Sex on the beach',
    'Private Stars',
    'Tight and Teen',
]


def _site(name: str) -> SiteInfo:
    return SiteInfo(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=PROVIDER_BASE_URL,
        search_path=PROVIDER_SEARCH_PATH,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_config=ScraperConfig(type='private'),
    )


PRIVATE_SITES: list[SiteInfo] = [_site(n) for n in _NAMES]
