from __future__ import annotations

from phoenixadult.registry.selectors._factory import make_site
from phoenixadult.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'VNA Network'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''


def _site(name: str, host: str, search_path: str = '/videos/') -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path=search_path,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='vna',
    )


VNA_SITES: list[SiteInfo] = [
    _site('All Anal All the Time', 'allanalallthetime.com'),
    _site('Kimber Lee Live', 'kimberleelive.com'),
    _site('Vicky at Home', 'vickyathome.com', '/milf-videos/'),
    _site('Shanda Fay', 'shandafay.com'),
    _site('Deauxma Live', 'deauxmalive.com'),
    _site('Sara Jay', 'sarajay.com'),
    _site('Carmen Valentina', 'carmenvalentina.com'),
    _site('Charlee Chase Live', 'charleechaselive.com'),
    _site('Gabby Quinteros', 'gabbyquinteros.com'),
    _site('Angelina Castro Live', 'angelinacastrolive.com'),
    _site('Julia Ann Live', 'juliaannlive.com'),
    _site('Nikki Benz', 'nikkibenz.com'),
    _site('Sunny Lane Live', 'sunnylanelive.com'),
    _site('Puma Swede XXX', 'pumaswedexxx.com'),
    _site('Sophie Dee Live', 'sophiedeelive.com'),
    _site('Its Cleo Live', 'itscleolive.com'),
    _site('Maggie Green Live', 'maggiegreenlive.com'),
    _site('Bobbi Eden Live', 'bobbiedenlive.com'),
    _site('Eva Lin Live', 'evalin.live'),
    _site('Tasha Reign', 'tashareign.com'),
    _site('Jelena Jensen', 'jelenajensen.com'),
    _site('Penny Pax Live', 'pennypaxlive.com'),
    _site('Sex My Wife', 'sexmywife.com'),
    _site('Rubber Doll', 'rubberdoll.net'),
    _site('Fucked Feet', 'fuckedfeet.com'),
    _site('Nina Kayy', 'ninakayy.com'),
    _site('Rome Major', 'romemajor.com'),
    _site('Siri', 'siripornstar.com'),
    _site('Kink305', 'kink305.com'),
    _site('Foxxed Up', 'foxxedup.com'),
    _site('Natalia Starr', 'nataliastarr.com'),
    _site('Samantha Grace', 'samanthagrace.com'),
    _site('Rachel Storms XXX', 'rachelstormsxxx.com'),
    _site('Kendra James', 'kendrajames.com'),
    _site('Maxine X', 'maxinex.com'),
    _site('POV Mania', 'povmania.com'),
    _site('Girl Girl Mania', 'girlgirlmania.com'),
    _site('Kayla Paige Live', 'kaylapaigelive.com'),
    _site('Women By Julia Ann', 'womenbyjuliaann.com'),
    _site('VNA Live', 'vnalive.com'),
]
