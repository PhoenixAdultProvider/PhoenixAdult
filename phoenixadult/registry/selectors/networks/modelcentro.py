from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'ModelCentro Network'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SCENE_TEMPLATE = '{base}/scene/{id}/'
PROVIDER_SEARCH_PATH = '/sapi/'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Fall in Lovia', host='www.fallinlovia.com'),
    PROVIDER.site('Romi Rain', host='www.romirain.com'),
    PROVIDER.site('Jerk Off with Me', host='www.jerkoffwithme.com'),
    PROVIDER.site('Get Your Knees Dirty', host='www.getyourkneesdirty.com'),
    PROVIDER.site('Nude Beauties', host='nudebeauties.eu'),
    PROVIDER.site('Dani Daniels', host='danidaniels.com'),
    PROVIDER.site('Official Chloe Toy', host='officialchloetoy.com'),
    PROVIDER.site('Yummy Couple', host='friends.yummycouple.com'),
    PROVIDER.site('Katya Clover', host='www.katya-clover.com'),
    PROVIDER.site('De Nude Art', host='denudeart.com'),
    PROVIDER.site('Lisey Sweet', host='theliseysweet.com'),
    PROVIDER.site('My Life in Miami', host='mylifeinmiami.com'),
    PROVIDER.site('Gina Gerson', host='www.ginagerson.xxx'),
    PROVIDER.site('Vina Sky XXX', host='www.vinaskyxxx.com'),
    PROVIDER.site('Bruce and Morgan', host='www.bruceandmorgan.net'),
    PROVIDER.site('Vicki Valkyrie', host='www.vickivalkyrie.com'),
    PROVIDER.site('Dillion Nation', host='dillionation.com'),
    PROVIDER.site('Lilu Moon', host='www.lilumoonx.com'),
    PROVIDER.site('SlutInspection', host='www.slutinspection.com'),
]
