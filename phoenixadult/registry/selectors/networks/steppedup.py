from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site

PROVIDER_NAME = 'Stepped Up Media'
PROVIDER_CONTENT_TYPE: ContentType = 'actors'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = 'Actor only'


def _site(name: str, host: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path='',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='steppedup',
        direct_url_template='{base}/scenes/{head}',
    )


STEPPEDUP_SITES: list[SiteInfo] = [
    _site('Swallowed', 'tour.swallowed.com'),
    _site('True Anal', 'tour.trueanal.com'),
    _site('Nympho', 'tour.nympho.com'),
    _site('All Anal', 'tour.allanal.com'),
    _site('Anal Only', 'tour.analonly.com'),
    _site('Dirty Auditions', 'dirtyauditions.com'),
]
