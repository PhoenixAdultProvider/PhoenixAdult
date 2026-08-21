from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site

PROVIDER_NAME = 'Spizoo'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = ''
_SEARCH_PATH = '/search.php?query={query}'


def _site(name: str, host: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path=_SEARCH_PATH,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='spizoo',
    )


def _spizoo(name: str) -> SiteInfo:
    return _site(name, 'www.spizoo.com')


SPIZOO_SITES: list[SiteInfo] = [
    _spizoo('Spizoo'),
    _spizoo('First Class POV'),
    _spizoo('Intimate Lesbians'),
    _spizoo('The Stripper Experience'),
    _spizoo('Porn Goes Pro'),
    _spizoo('Jessica Jaymes XXX'),
    _spizoo('Pornstar Tease'),
    _site('Raw Attack', 'www.rawattack.com'),
    _site('Mr. Lucky POV', 'www.mrluckypov.com'),
    _site('Mr. Lucky RAW', 'www.mrluckyraw.com'),
    _site('Mr. Lucky LIFE', 'www.mrluckylife.com'),
    _site('Cream Her', 'www.creamher.com'),
    _site('DR. Daddy POV', 'www.drdaddypov.com'),
    _site('Goth Girlfriends', 'www.gothgirlfriends.com'),
]
