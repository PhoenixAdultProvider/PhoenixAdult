from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = '5Kporn'
PROVIDER_BASE_URL = 'https://www.5kporn.com'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/episodes/search?search={query}'
PROVIDER_IMAGE_REFERERS = ['sceneURL']
PROVIDER_IMAGE_COOKIES = ['nats=MC4wLjMuNTguMC4wLjAuMC4w; ageConfirmed=true']
PROVIDER_SCRAPER_TYPE = '5kporn'
PROVIDER_DATA18_ENRICHMENT = True

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [PROVIDER.site('5Kporn'), PROVIDER.site('5Kteens')]
