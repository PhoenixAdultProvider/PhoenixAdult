from __future__ import annotations

from app.registry.selectors._factory import make_site
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Strike3'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = 'Impersonate Required'


def _site(name: str, host: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://www.{host}',
        search_path='',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='strike3',
        data18_enrichment=True,
        cache_layout='network',
    )


STRIKE3_SITES: list[SiteInfo] = [
    _site('Blacked', 'blacked.com'),
    _site('Blacked RAW', 'blackedraw.com'),
    _site('Vixen', 'vixen.com'),
    _site('Tushy', 'tushy.com'),
    _site('Tushy RAW', 'tushyraw.com'),
    _site('Deeper', 'deeper.com'),
    _site('Slayed', 'slayed.com'),
    _site('Milfy', 'milfy.com'),
    _site('Wifey', 'wifey.com'),
]
