from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'PornCZ'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = 'Title or Actor'
PROVIDER_IMAGE_REFERERS = ['baseURL']
PROVIDER_SEARCH_PATH = '/en/search?q={query}'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Czech Sex Casting', host='www.czechsexcasting.com'),
    PROVIDER.site('Sex with Muslims', host='www.sexwithmuslims.com'),
    PROVIDER.site('Sex in Taxi', host='www.sexintaxi.com'),
    PROVIDER.site('VR Porn CZ', host='www.vrporncz.com'),
    PROVIDER.site('Fucking Street', host='www.fuckingstreet.com'),
    PROVIDER.site('Hunter POV', host='www.hunterpov.com'),
    PROVIDER.site('Czech Gypsies', host='www.czechgypsies.com'),
    PROVIDER.site('Dick on Trip', host='www.dickontrip.com'),
    PROVIDER.site('Czech Boobs', host='www.czechboobs.com'),
    PROVIDER.site('Czech Deviant', host='www.czechdeviant.com'),
    PROVIDER.site('Amateri Premium', host='www.amateripremium.com'),
    PROVIDER.site('Fucking Office', host='www.fuckingoffice.com'),
    PROVIDER.site('Czech Executor', host='www.czechexecutor.com'),
    PROVIDER.site('Czech Hitchhikers', host='www.czechhitchhikers.com'),
    PROVIDER.site('Girls Take Away', host='www.girlstakeaway.com'),
    PROVIDER.site('Czech Escort Girls', host='www.czechescortgirls.com'),
    PROVIDER.site('Horny Doctor', host='www.hornydoctor.com'),
    PROVIDER.site('Lady Dee', host='www.ladydee.com'),
    PROVIDER.site('Teen From Bohemia', host='www.teenfrombohemia.com'),
    PROVIDER.site('Czech Real Dolls', host='www.czechrealdolls.com'),
    PROVIDER.site('Amateur From Bohemia', host='www.amateursfrombohemia.com'),
    PROVIDER.site('Czech Anal Sex', host='www.czechanalsex.com'),
    PROVIDER.site('Dellia Twins', host='www.dellaitwins.com'),
    PROVIDER.site('Chloe Lamour', host='www.chloelamour.com'),
    PROVIDER.site('Public From Bohemia', host='www.publicfrombohemia.com'),
    PROVIDER.site('Susan Ayn', host='www.susanayn.com'),
    PROVIDER.site('Horny Girls CZ', host='www.hornygirlscz.com'),
    PROVIDER.site('Czech Sex Party', host='www.czechsexparty.com'),
    PROVIDER.site('Retro Porn CZ', host='www.retroporncz.com'),
    PROVIDER.site('Boys Fuck MILFs', host='www.boysfuckmilfs.com'),
    PROVIDER.site('Czech Bi Porn', host='www.czechbiporn.com'),
    PROVIDER.site('Czech Shemale', host='www.czechshemale.com'),
    PROVIDER.site('Czech Gay City', host='www.czechgaycity.com'),
]
