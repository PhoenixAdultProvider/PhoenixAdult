from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider
from phoenixadult.utils.helpers.data_files import load_data

PROVIDER_NAME = 'BellaPass'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = 'Title or Slug'
PROVIDER_SEARCH_PATH = '/search.php?query={query}'

_ALIASES: list[str] = load_data(__file__, 'bellapass_aliases')

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('BellaPass', host='bellapass.com', aliases=_ALIASES),
    PROVIDER.site('Hussie Pass', host='hussiepass.com'),
    PROVIDER.site('Babe Archives', host='babearchives.com'),
    PROVIDER.site('See Him Fuck', host='seehimfuck.com'),
]
