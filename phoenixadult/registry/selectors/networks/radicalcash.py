from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site

PROVIDER_NAME = 'Radical Cash'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''


def _site(name: str, host: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path='',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='radicalcash',
    )


SITES: list[SiteInfo] = [
    _site('WankItNow', 'wankitnow.com'),
    _site('BoppingBabes', 'boppingbabes.com'),
    _site('UpskirtJerk', 'upskirtjerk.com'),
    _site('Top Web Models', 'tour.topwebmodels.com'),
    _site('Big Gulp Girls', 'tour.biggulpgirls.com'),
    _site('2 Girls 1 Camera', 'tour.2girls1camera.com'),
    _site('Cougar Season', 'tour.cougarseason.com'),
    _site('Deepthroat Sirens', 'tour.deepthroatsirens.com'),
    _site('Facials Forever', 'tour.facialsforever.com'),
    _site('Pounded Petite', 'tour.poundedpetite.com'),
    _site("She's Brand New", 'tour.shesbrandnew.com'),
    _site('Sexy Modern Bull', 'sexymodernbull.com'),
    _site('GotFilled', 'gotfilled.com'),
    _site('Come Inside', 'comeinside.com'),
    _site('Benefit Monkey', 'benefitmonkey.com'),
    _site("Ricky's Room", 'rickysroom.com'),
    _site('Inserted', 'inserted.com'),
    _site('BJ Raw', 'bjraw.com'),
    _site('AltErotic', 'alterotic.com'),
    _site('Lezkey', 'lezkey.com'),
    _site('SIDECHICK', 'sidechick.com'),
    _site('JAV888', 'jav888.com'),
    _site('Divine-DD', 'divine-dd.com'),
    _site('DownblouseJerk', 'downblousejerk.com'),
    _site('RealBikiniGirls', 'realbikinigirls.com'),
    _site('LingerieTales', 'lingerietales.com'),
    _site('POV Perv', 'tour.povperv.com'),
    _site('LegendaryX', 'legendaryx.com'),
    _site('Amazing Films', 'amazingfilms.com'),
    _site('Lucid Flix', 'lucidflix.com'),
    _site('Nick Marxx', 'nickmarxx.com'),
    _site('BlackBullChallenge', 'blackbullchallenge.com'),
    _site('Dark Shade', 'darkshade.com'),
    _site('Dick HD Daily', 'dickhddaily.com'),
    _site('Dire Desires', 'diredesires.com'),
    _site('Purity VR', 'purityvr.com'),
    _site('Passion POV', 'passionpov.com'),
    _site('Queer Crush', 'queercrush.com'),
    _site('Hard Werk', 'hardwerk.com'),
    _site('Cannon Prod', 'cannonprod.com'),
    _site('Bemefi', 'bemefi.com'),
    _site('FreakMobMedia', 'freakmobmedia.com'),
    _site('XFul', 'xful.com'),
    _site('S3XUS', 's3xus.com'),
    _site('Yes Girlz', 'yesgirlz.com'),
    _site('Z Filmz Originals', 'z-filmz-originals.com'),
    _site('Hoby Buchanon', 'hobybuchanon.com'),
    _site('VRHush', 'vrhush.com'),
]
