from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site

PROVIDER_NAME = 'MissaX'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = ''


def _site(name: str, base_url: str, search_path: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=base_url,
        search_path=search_path,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='missax',
    )


MISSAX_SITES: list[SiteInfo] = [
    _site('MissaX', 'https://missax.com', '/tour/search.php?query={query}'),
    _site('AllHerLuv', 'https://allherluv.com', '/tour/search.php?query={query}'),
    _site('Exposed Whores', 'https://exposedwhores.com/new-tour', '/search.php?query={query}'),
    _site('She Seduced Me', 'https://www.sheseducedme.com', '/search.php?query={query}'),
    _site('House of Fyre', 'https://www.houseofyre.com', '/search.php?query={query}'),
    _site('Philavise', 'https://www.philavise.com', '/search.php?query={query}'),
    _site('Lauren Phillips', 'https://laurenphillips.com', '/search.php?query={query}'),
]
