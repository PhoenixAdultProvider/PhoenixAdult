from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Gamma'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/en/search/scene/'
PROVIDER_BASE_URL = 'http://www.{host}'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Tera Patrick', host='terapatrick.com', search_path='/en/search/', sub_group='Fame Digital'),
    PROVIDER.site('Sunny Leone', host='sunnyleone.com', sub_group='Open Life Network'),
    PROVIDER.site('Lane Sisters', host='lanesisters.com', sub_group='Open Life Network'),
    PROVIDER.site('Dylan Ryder', host='dylanryder.com', sub_group='Open Life Network'),
    PROVIDER.site('Abbey Brooks', host='abbeybrooks.com', sub_group='Open Life Network'),
    PROVIDER.site('Devon Lee', host='devonlee.com', sub_group='Open Life Network'),
    PROVIDER.site('Hanna Hilton', host='hannahilton.com', sub_group='Open Life Network'),
]
