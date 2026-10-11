from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Spizoo'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/search.php?query={query}'

PROVIDER = Provider.from_headers(__name__)


def _spizoo(name: str) -> SiteInfo:
    return PROVIDER.site(name, host='www.spizoo.com')


SITES: list[SiteInfo] = [
    _spizoo('Spizoo'),
    _spizoo('First Class POV'),
    _spizoo('Intimate Lesbians'),
    _spizoo('The Stripper Experience'),
    _spizoo('Porn Goes Pro'),
    _spizoo('Jessica Jaymes XXX'),
    _spizoo('Pornstar Tease'),
    PROVIDER.site('Raw Attack', host='www.rawattack.com'),
    PROVIDER.site('Mr. Lucky POV', host='www.mrluckypov.com'),
    PROVIDER.site('Mr. Lucky RAW', host='www.mrluckyraw.com'),
    PROVIDER.site('Mr. Lucky LIFE', host='www.mrluckylife.com'),
    PROVIDER.site('Cream Her', host='www.creamher.com'),
    PROVIDER.site('DR. Daddy POV', host='www.drdaddypov.com'),
    PROVIDER.site('Goth Girlfriends', host='www.gothgirlfriends.com'),
]
