from __future__ import annotations

from app.models.scraper_config import ScraperConfig
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'VIP4K'
PROVIDER_BASE_URL = 'https://vip4k.com'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''

_NAMES = [
    'Tutor 4k',
    'Daddy 4k',
    'Stuck 4k',
    'Old 4k',
    'Hunt 4k',
    'Sis',
    'Black 4k',
    'Loan 4k',
    'Debt 4k',
    'Rim 4k',
    'Fist 4k',
    'Mature 4k',
    'Shame 4k',
    'Pie 4k',
    'VIP4K',
    'Bride 4K',
    'Dyke 4K',
    'Ignore 4K',
    'Cuck 4K',
    'Mommy 4K',
    'Serve 4K',
]


def _site(name: str) -> SiteInfo:
    return SiteInfo(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=PROVIDER_BASE_URL,
        search_path='/en/search/{query}',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_config=ScraperConfig(type='vip4k'),
    )


VIP4K_SITES: list[SiteInfo] = [_site(n) for n in _NAMES]
