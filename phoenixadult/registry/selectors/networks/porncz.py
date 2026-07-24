from __future__ import annotations

from phoenixadult.registry.selectors._factory import make_site
from phoenixadult.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'PornCZ'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = 'Title or Actor'


def _site(name: str, host: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path='/en/search?q={query}',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        image_referers=['baseURL'],
        scraper_type='porncz',
    )


PORNCZ_SITES: list[SiteInfo] = [
    _site('Czech Sex Casting', 'www.czechsexcasting.com'),
    _site('Sex with Muslims', 'www.sexwithmuslims.com'),
    _site('Sex in Taxi', 'www.sexintaxi.com'),
    _site('VR Porn CZ', 'www.vrporncz.com'),
    _site('Fucking Street', 'www.fuckingstreet.com'),
    _site('Hunter POV', 'www.hunterpov.com'),
    _site('Czech Gypsies', 'www.czechgypsies.com'),
    _site('Dick on Trip', 'www.dickontrip.com'),
    _site('Czech Boobs', 'www.czechboobs.com'),
    _site('Czech Deviant', 'www.czechdeviant.com'),
    _site('Amateri Premium', 'www.amateripremium.com'),
    _site('Fucking Office', 'www.fuckingoffice.com'),
    _site('Czech Executor', 'www.czechexecutor.com'),
    _site('Czech Hitchhikers', 'www.czechhitchhikers.com'),
    _site('Girls Take Away', 'www.girlstakeaway.com'),
    _site('Czech Escort Girls', 'www.czechescortgirls.com'),
    _site('Horny Doctor', 'www.hornydoctor.com'),
    _site('Lady Dee', 'www.ladydee.com'),
    _site('Teen From Bohemia', 'www.teenfrombohemia.com'),
    _site('Czech Real Dolls', 'www.czechrealdolls.com'),
    _site('Amateur From Bohemia', 'www.amateursfrombohemia.com'),
    _site('Czech Anal Sex', 'www.czechanalsex.com'),
    _site('Dellia Twins', 'www.dellaitwins.com'),
    _site('Chloe Lamour', 'www.chloelamour.com'),
    _site('Public From Bohemia', 'www.publicfrombohemia.com'),
    _site('Susan Ayn', 'www.susanayn.com'),
    _site('Horny Girls CZ', 'www.hornygirlscz.com'),
    _site('Czech Sex Party', 'www.czechsexparty.com'),
    _site('Retro Porn CZ', 'www.retroporncz.com'),
    _site('Boys Fuck MILFs', 'www.boysfuckmilfs.com'),
    _site('Czech Bi Porn', 'www.czechbiporn.com'),
    _site('Czech Shemale', 'www.czechshemale.com'),
    _site('Czech Gay City', 'www.czechgaycity.com'),
]
