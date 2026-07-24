from __future__ import annotations

from phoenixadult.registry.selectors._factory import make_site
from phoenixadult.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Radical Cash Other'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''


def _site(name: str, host: str, search_path: str, sub_group: str, search_notes: str = PROVIDER_SEARCH_NOTES) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        sub_group=sub_group,
        base_url=f'https://{host}',
        search_path=search_path,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=search_notes,
        scraper_type='radicalcashother',
    )


def _hitzefrei(name: str, host: str) -> SiteInfo:
    return _site(name, host, '/search/{query}', 'Hitzefrei')


RADICALCASHOTHER_SITES: list[SiteInfo] = [
    _site('PurgatoryX', 'purgatoryx.com', 'https://tour.purgatoryx.com/search/{query}', 'PurgatoryX'),
    _site('Hitzefrei', 'hitzefrei.com', 'https://tour.hitzefrei.com/search/{query}', 'Hitzefrei'),
    _hitzefrei('Unleashed', 'unleashed.hitzefrei.com'),
    _hitzefrei('CityCheck', 'citycheck.hitzefrei.com'),
    _hitzefrei('MILF Hunters', 'milfhunters.hitzefrei.com'),
    _hitzefrei('Cuff Em All', 'cuffemall.hitzefrei.com'),
    _hitzefrei('fANALarm', 'fanalarm.hitzefrei.com'),
    _hitzefrei('Fuck on Arrival', 'fuckonarrival.hitzefrei.com'),
    _hitzefrei('Family Affairs', 'familyaffairs.hitzefrei.com'),
    _hitzefrei("Patti's Anal", 'pattisanals.hitzefrei.com'),
    _site('Gonzo Living', 'gonzoliving.com', 'https://tour.gonzoliving.com/search/{query}', 'Gonzo Living'),
    _site('Teen Gonzo', 'teengonzo.com', 'https://tour.teengonzo.com/search/{query}', 'Gonzo Living'),
    _site('MILF Gonzo', 'milfgonzo.com', 'https://tour.milfgonzo.com/search/{query}', 'Gonzo Living'),
    _site('ToughLoveX', 'toughlovex.com', 'https://tour.toughlovex.com/search/{query}', 'ToughLoveX', 'Actor Name Only or Title Only'),
]
