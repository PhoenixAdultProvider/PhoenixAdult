from __future__ import annotations

from phoenixadult.registry.selectors._factory import make_site
from phoenixadult.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Cherry Pimps'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/search.php?query={query}'
_DEFAULT_BASE = 'https://www.cherrypimps.com'


def _site(name: str, base_url: str = _DEFAULT_BASE) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=base_url,
        search_path=PROVIDER_SEARCH_PATH,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='cherrypimps',
    )


CHERRYPIMPS_SITES: list[SiteInfo] = [
    _site('Cherry Pimps'),
    _site('Wild On Cam', 'https://www.wildoncam.com'),
    _site('Cherry Spot'),
    _site('Britney Amber'),
    _site('Confessions.XXX'),
    _site('Cucked.XXX'),
    _site('Drilled.XXX'),
    _site('BCM.XXX'),
    _site('Petite.XXX'),
    _site('Family'),
    _site('Busted'),
    _site('Cheese.XXX'),
    _site('Femme'),
    _site('Fresh'),
    _site('Taboo'),
    _site('Bush'),
    _site('Ginger'),
]
