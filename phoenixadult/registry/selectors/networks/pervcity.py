from __future__ import annotations

from phoenixadult.registry.selectors._factory import make_site
from phoenixadult.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'PervCity'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = 'Title or Actor'


def _site(name: str, host: str, search_path: str = '/search.php?query={query}') -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path=search_path,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='pervcity',
    )


PERVCITY_SITES: list[SiteInfo] = [
    _site('Anal Overdose', 'analoverdose.com'),
    _site('Banging Beauties', 'www.bangingbeauties.com'),
    _site('Chocolate BJs', 'www.chocolatebjs.com'),
    _site('Oral Overdose', 'www.oraloverdose.com'),
    _site('Up Her Asshole', 'www.upherasshole.com'),
    _site('Perv City', 'www.pervcity.com'),
    _site('DP Diva', 'www.dpdiva.com', ''),
]
