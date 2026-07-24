from __future__ import annotations

from phoenixadult.registry.selectors._factory import make_site
from phoenixadult.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'ModelCentro Network'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''


def _site(name: str, base_url: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=base_url,
        search_path='/sapi/',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='modelcentro',
    )


MODELCENTRO_SITES: list[SiteInfo] = [
    _site('Fall In Lovia', 'https://www.fallinlovia.com'),
    _site('Romi Rain', 'https://www.romirain.com'),
    _site('Jerk Off With Me', 'https://www.jerkoffwithme.com'),
    _site('Get Your Knees Dirty', 'https://www.getyourkneesdirty.com'),
    _site('Nude Beauties', 'https://nudebeauties.eu'),
    _site('Dani Daniels', 'https://danidaniels.com'),
    _site('Official Chloe Toy', 'https://officialchloetoy.com'),
    _site('Yummy Couple', 'https://friends.yummycouple.com'),
    _site('Katya Clover', 'https://www.katya-clover.com'),
    _site('De Nude Art', 'https://denudeart.com'),
    _site('Lisey Sweet', 'https://theliseysweet.com'),
    _site('My Life In Miami', 'https://mylifeinmiami.com'),
    _site('Gina Gerson', 'https://www.ginagerson.xxx'),
    _site('Vina Sky XXX', 'https://www.vinaskyxxx.com'),
    _site('Bruce and Morgan', 'https://www.bruceandmorgan.net'),
    _site('Vicki Valkyrie', 'https://www.vickivalkyrie.com'),
    _site('Dillion Nation', 'https://dillionation.com'),
    _site('Lilu Moon', 'https://www.lilumoonx.com'),
    _site('SlutInspection', 'https://www.slutinspection.com'),
]
