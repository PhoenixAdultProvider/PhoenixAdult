from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider
from phoenixadult.utils.helpers.data_files import load_data

PROVIDER_NAME = 'FAKings'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''

_ALIASES: list[str] = load_data(__file__, 'fakings_aliases')

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site(PROVIDER_NAME, host='www.fakings.com', search_path='/en/buscar/{query}', aliases=_ALIASES),
]
