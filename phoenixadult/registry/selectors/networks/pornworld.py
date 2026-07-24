from __future__ import annotations

from phoenixadult.registry.selectors._factory import make_site
from phoenixadult.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'PornWorld'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''


def _site(name: str, host: str, search_path: str = '/videos/freeword/{query}') -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path=search_path,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='pornworld',
    )


PORNWORLD_SITES: list[SiteInfo] = [
    _site('DDF Babes', 'ddfnetwork.com'),
    _site('DDFNetwork', 'ddfnetwork.com'),
    _site('Sandys Fantasies', 'ddfnetwork.com'),
    _site('Cherry Jul', 'ddfnetwork.com'),
    _site('Eve Angel Official', 'ddfnetwork.com'),
    _site('Sex Video Casting', 'ddfnetwork.com'),
    _site('Hairy Twatter', 'ddfnetwork.com'),
    _site('DDF Xtreme', 'ddfnetwork.com'),
    _site('DDF Busty', 'ddfbusty.com'),
    _site('House of Taboo', 'houseoftaboo.com'),
    _site('Euro Girls on Girls', 'eurogirlsongirls.com'),
    _site('1ByDay', '1by-day.com'),
    _site('Euro Teen Erotica', 'euroteenerotica.com'),
    _site('Hot Legs and Feet', 'hotlegsandfeet.com'),
    _site('Only Blowjob', 'onlyblowjob.com'),
    _site('Hands on Hardcore', 'handsonhardcore.com'),
    _site('PornWorld', 'pornworld.com', '/search/{query}'),
]
