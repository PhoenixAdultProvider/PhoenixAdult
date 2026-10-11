from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'VNA Network'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/videos/'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('All Anal All the Time', host='allanalallthetime.com'),
    PROVIDER.site('Kimber Lee Live', host='kimberleelive.com'),
    PROVIDER.site('Vicky at Home', host='vickyathome.com', search_path='/milf-videos/'),
    PROVIDER.site('Shanda Fay', host='shandafay.com'),
    PROVIDER.site('Deauxma Live', host='deauxmalive.com'),
    PROVIDER.site('Sara Jay', host='sarajay.com'),
    PROVIDER.site('Carmen Valentina', host='carmenvalentina.com'),
    PROVIDER.site('Charlee Chase Live', host='charleechaselive.com'),
    PROVIDER.site('Gabby Quinteros', host='gabbyquinteros.com'),
    PROVIDER.site('Angelina Castro Live', host='angelinacastrolive.com'),
    PROVIDER.site('Julia Ann Live', host='juliaannlive.com'),
    PROVIDER.site('Nikki Benz', host='nikkibenz.com'),
    PROVIDER.site('Sunny Lane Live', host='sunnylanelive.com'),
    PROVIDER.site('Puma Swede XXX', host='pumaswedexxx.com'),
    PROVIDER.site('Sophie Dee Live', host='sophiedeelive.com'),
    PROVIDER.site('Its Cleo Live', host='itscleolive.com'),
    PROVIDER.site('Maggie Green Live', host='maggiegreenlive.com'),
    PROVIDER.site('Bobbi Eden Live', host='bobbiedenlive.com'),
    PROVIDER.site('Eva Lin Live', host='evalin.live'),
    PROVIDER.site('Tasha Reign', host='tashareign.com'),
    PROVIDER.site('Jelena Jensen', host='jelenajensen.com'),
    PROVIDER.site('Penny Pax Live', host='pennypaxlive.com'),
    PROVIDER.site('Sex My Wife', host='sexmywife.com'),
    PROVIDER.site('Rubber Doll', host='rubberdoll.net'),
    PROVIDER.site('Fucked Feet', host='fuckedfeet.com'),
    PROVIDER.site('Nina Kayy', host='ninakayy.com'),
    PROVIDER.site('Rome Major', host='romemajor.com'),
    PROVIDER.site('Siri', host='siripornstar.com'),
    PROVIDER.site('Kink305', host='kink305.com'),
    PROVIDER.site('Foxxed Up', host='foxxedup.com'),
    PROVIDER.site('Natalia Starr', host='nataliastarr.com'),
    PROVIDER.site('Samantha Grace', host='samanthagrace.com'),
    PROVIDER.site('Rachel Storms XXX', host='rachelstormsxxx.com'),
    PROVIDER.site('Kendra James', host='kendrajames.com'),
    PROVIDER.site('Maxine X', host='maxinex.com'),
    PROVIDER.site('POV Mania', host='povmania.com'),
    PROVIDER.site('Girl Girl Mania', host='girlgirlmania.com'),
    PROVIDER.site('Kayla Paige Live', host='kaylapaigelive.com'),
    PROVIDER.site('Women by Julia Ann', host='womenbyjuliaann.com'),
    PROVIDER.site('VNA Live', host='vnalive.com'),
]
