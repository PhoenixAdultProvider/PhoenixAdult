from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site

PROVIDER_NAME = 'High-Tech VR'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'exact'


def _site(name: str, host: str, search_path: str, search_notes: str = '') -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path=f'{search_path}/{{query}}',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=search_notes,
        scraper_type='hightechvr',
    )


SITES: list[SiteInfo] = [
    _site('SexBabesVR', 'sexbabesvr.com', '/video', 'Direct URL'),
    _site('StasyQ VR', 'stasyqvr.com', '/virtualreality/scene/id', 'SceneID'),
    _site('RealJamVR', 'realjamvr.com', '/scene', 'Direct URL'),
]
