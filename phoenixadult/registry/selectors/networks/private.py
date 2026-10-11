from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

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
    'Sex on the Beach',
    'Private Stars',
    'Tight and Teen',
]

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [PROVIDER.site(n) for n in _NAMES]
