from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider
from phoenixadult.utils.helpers.data_files import load_data

PROVIDER_NAME = 'Abby Winters'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = 'Actor only'

_ALIASES: list[str] = load_data(__file__, 'abbywinters_aliases')

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site(
        PROVIDER_NAME, host='www.abbywinters.com', search_path='/amateurs/models?filters%5Bkeyword%5D={query}', aliases=_ALIASES, image_referers=['baseurl']
    ),
]
