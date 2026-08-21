from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site

PROVIDER_NAME = '5Kporn'
PROVIDER_BASE_URL = 'https://www.5kporn.com'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/episodes/search?search={query}'
_IMAGE_COOKIE = 'nats=MC4wLjMuNTguMC4wLjAuMC4w; ageConfirmed=true'


def _site(name: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=PROVIDER_BASE_URL,
        search_path=PROVIDER_SEARCH_PATH,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        image_referers=['sceneURL'],
        image_cookies=[_IMAGE_COOKIE],
        scraper_type='5kporn',
        data18_enrichment=True,
    )


SITES: list[SiteInfo] = [_site('5Kporn'), _site('5Kteens')]
