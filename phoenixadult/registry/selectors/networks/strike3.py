from __future__ import annotations

from phoenixadult.models.site_info import BypassName, ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site

PROVIDER_NAME = 'Strike3'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_BYPASS: list[BypassName] = ['Impersonate']


def _site(name: str, host: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://www.{host}',
        search_path='',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        bypass=PROVIDER_BYPASS,
        scraper_type='strike3',
        data18_enrichment=True,
        direct_url_template='{base}/videos/{head}',
    )


SITES: list[SiteInfo] = [
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
