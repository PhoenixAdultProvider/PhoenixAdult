from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'VIP4K'
PROVIDER_BASE_URL = 'https://vip4k.com'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/en/search/{query}'

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

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [PROVIDER.site(n) for n in _NAMES]
