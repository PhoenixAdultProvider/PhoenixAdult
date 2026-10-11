from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider
from phoenixadult.utils.helpers.data_files import load_data

PROVIDER_NAME = 'Archive'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = 'Cached Scenes Only — Site Retired'
PROVIDER_BASE_URL = ''
PROVIDER_SEARCH_PATH = ''

PROVIDER = Provider.from_headers(__name__)

ARCHIVE_SITES: list[SiteInfo] = [PROVIDER.site(name) for name in load_data(__file__, 'archive_sites')]
