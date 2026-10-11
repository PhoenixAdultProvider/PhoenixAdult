from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider
from phoenixadult.registry.selectors.networks.reptyle_networks import reptyle_aliases

PROVIDER_NAME = 'Reptyle'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/movies/{query}'
PROVIDER_DATA18_ENRICHMENT = True
PROVIDER_SCENE_TEMPLATE = '{base}/movies/{head}'

_ALIASES: dict[str, list[str]] = reptyle_aliases()

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('MYLF', base_url='https://www.mylf.com', aliases=_ALIASES.get('MYLF', [])),
    PROVIDER.site('TeamSkeet', base_url='https://www.teamskeet.com', token_prefixes=('mylfx', 'teamskeetx'), aliases=_ALIASES.get('TeamSkeet', [])),
    PROVIDER.site('Swappz', base_url='https://www.swappz.com', aliases=_ALIASES.get('Swappz', [])),
    PROVIDER.site('FreeUse', base_url='https://www.freeuse.com', aliases=_ALIASES.get('FreeUse', [])),
    PROVIDER.site('Pervz', base_url='https://www.pervz.com', aliases=_ALIASES.get('Pervz', [])),
    PROVIDER.site('Family Strokes', base_url='https://www.familystrokes.com', aliases=_ALIASES.get('Family Strokes', [])),
]
