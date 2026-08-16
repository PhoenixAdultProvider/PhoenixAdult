from __future__ import annotations

from phoenixadult.registry.selectors._factory import make_site
from phoenixadult.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Caramel Cash'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'exact'
PROVIDER_SEARCH_NOTES = 'Scene ID'


def _site(name: str, host: str, search_path: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path=f'{search_path}/{{query}}',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='caramelcash',
    )


CARAMELCASH_SITES: list[SiteInfo] = [
    _site('VR PMV Bay', 'vrpmvbay.com', '/video'),
    _site('Cuckold Wish', 'cuckoldwish.com', '/videos'),
    _site('Alex Legend', 'alexlegend.com', '/video'),
]
