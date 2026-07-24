from __future__ import annotations

from phoenixadult.registry.selectors._factory import make_site
from phoenixadult.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'BaDoink VR'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''


def _site(name: str, host: str, search_path: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path=f'{search_path}/{{query}}',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='badoinkvr',
        data18_enrichment=True,
    )


BADOINKVR_SITES: list[SiteInfo] = [
    _site('BaDoinkVR', 'badoinkvr.com', '/vrpornvideos/search'),
    _site('BabeVR', 'babevr.com', '/vrpornvideos/search'),
    _site('18VR', '18vr.com', '/vrpornvideos/search'),
    _site('VRCosplayX', 'vrcosplayx.com', '/cosplaypornvideos/search'),
    _site('PassthroughVR', 'realvr.com', '/vrpornvideos/search'),
]
