from __future__ import annotations

from phoenixadult.registry.selectors._factory import make_site
from phoenixadult.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'VIP4K'
PROVIDER_BASE_URL = 'https://vip4k.com'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''

_NAMES = [
    'Tutor 4K',
    'Daddy 4K',
    'Stuck 4K',
    'Old 4K',
    'Hunt 4K',
    'Sis',
    'Black 4K',
    'Loan 4K',
    'Debt 4K',
    'Rim 4K',
    'Fist 4K',
    'Mature 4K',
    'Shame 4K',
    'Pie 4K',
    'VIP4K',
    'Bride 4K',
    'Dyke 4K',
    'Ignore 4K',
    'Cuck 4K',
    'Mommy 4K',
    'Serve 4K',
]


def _site(name: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=PROVIDER_BASE_URL,
        search_path='/en/search/{query}',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='vip4k',
    )


VIP4K_SITES: list[SiteInfo] = [_site(n) for n in _NAMES]
