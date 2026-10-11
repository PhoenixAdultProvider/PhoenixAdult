from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'PornWorld'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/videos/freeword/{query}'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('DDF Babes', host='ddfnetwork.com'),
    PROVIDER.site('DDFNetwork', host='ddfnetwork.com'),
    PROVIDER.site('Sandys Fantasies', host='ddfnetwork.com'),
    PROVIDER.site('Cherry Jul', host='ddfnetwork.com'),
    PROVIDER.site('Eve Angel Official', host='ddfnetwork.com'),
    PROVIDER.site('Sex Video Casting', host='ddfnetwork.com'),
    PROVIDER.site('Hairy Twatter', host='ddfnetwork.com'),
    PROVIDER.site('DDF Xtreme', host='ddfnetwork.com'),
    PROVIDER.site('DDF Busty', host='ddfbusty.com'),
    PROVIDER.site('House of Taboo', host='houseoftaboo.com'),
    PROVIDER.site('Euro Girls on Girls', host='eurogirlsongirls.com'),
    PROVIDER.site('1ByDay', host='1by-day.com'),
    PROVIDER.site('Euro Teen Erotica', host='euroteenerotica.com'),
    PROVIDER.site('Hot Legs and Feet', host='hotlegsandfeet.com'),
    PROVIDER.site('Only Blowjob', host='onlyblowjob.com'),
    PROVIDER.site('Hands on Hardcore', host='handsonhardcore.com'),
    PROVIDER.site('PornWorld', host='pornworld.com', search_path='/search/{query}'),
]
