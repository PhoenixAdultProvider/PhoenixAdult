from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'LoveHerFilms'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/tour/search.php?query={query}'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('LoveHerFilms', host='www.loveherfilms.com'),
    PROVIDER.site('LoveHerBoobs', host='www.loveherboobs.com'),
    PROVIDER.site('LoveHerFeet', host='www.loveherfeet.com'),
    PROVIDER.site('SheLovesBlack', host='www.shelovesblack.com'),
]
