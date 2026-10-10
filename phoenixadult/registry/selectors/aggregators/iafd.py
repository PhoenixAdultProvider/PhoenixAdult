from __future__ import annotations

from typing import Literal

from phoenixadult.models.site_info import BypassName, ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site

PROVIDER_NAME = 'IAFD'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_BYPASS: list[BypassName] = ['Impersonate']
PROVIDER_BASE_URL = 'https://www.iafd.com'
PROVIDER_SCENE_TEMPLATE = f'{PROVIDER_BASE_URL}/title.rme/id={{head}}'

ListingType = Literal['studio', 'distrib']


def _site(name: str, listing_type: ListingType, listing_id: str, host: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=PROVIDER_BASE_URL,
        search_path=f'/{listing_type}.rme/{listing_type}={listing_id}/{host}.htm',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        bypass=PROVIDER_BYPASS,
        direct_url_template=PROVIDER_SCENE_TEMPLATE,
        scraper_type='iafd',
    )


SITES: list[SiteInfo] = [
    _site('Black Patrol', 'distrib', '9954', 'blackpatrol.com'),
]
