from __future__ import annotations

from app.registry.selectors._factory import make_site
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Unzip VR'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''


def _site(name: str, domain: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://content.{domain}',
        search_path='',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='unzipvr',
    )


UNZIPVR_SITES: list[SiteInfo] = [
    _site('VR Bangers', 'vrbangers.com'),
    _site('VR Conk', 'vrconk.com'),
    _site('Blow VR', 'blowvr.com'),
    _site('VRB Trans', 'vrbtrans.com'),
    _site('VRB Gay', 'vrbgay.com'),
]
