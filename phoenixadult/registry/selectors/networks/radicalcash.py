from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Radical Cash'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = ''

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('WankItNow', host='wankitnow.com'),
    PROVIDER.site('BoppingBabes', host='boppingbabes.com'),
    PROVIDER.site('UpskirtJerk', host='upskirtjerk.com'),
    PROVIDER.site('Top Web Models', host='tour.topwebmodels.com'),
    PROVIDER.site('Big Gulp Girls', host='tour.biggulpgirls.com'),
    PROVIDER.site('2 Girls 1 Camera', host='tour.2girls1camera.com'),
    PROVIDER.site('Cougar Season', host='tour.cougarseason.com'),
    PROVIDER.site('Deepthroat Sirens', host='tour.deepthroatsirens.com'),
    PROVIDER.site('Facials Forever', host='tour.facialsforever.com'),
    PROVIDER.site('Pounded Petite', host='tour.poundedpetite.com'),
    PROVIDER.site("She's Brand New", host='tour.shesbrandnew.com'),
    PROVIDER.site('Sexy Modern Bull', host='sexymodernbull.com'),
    PROVIDER.site('GotFilled', host='gotfilled.com'),
    PROVIDER.site('Come Inside', host='comeinside.com'),
    PROVIDER.site('Benefit Monkey', host='benefitmonkey.com'),
    PROVIDER.site("Ricky's Room", host='rickysroom.com'),
    PROVIDER.site('Inserted', host='inserted.com'),
    PROVIDER.site('BJ Raw', host='bjraw.com'),
    PROVIDER.site('AltErotic', host='alterotic.com'),
    PROVIDER.site('Lezkey', host='lezkey.com'),
    PROVIDER.site('SIDECHICK', host='sidechick.com'),
    PROVIDER.site('JAV888', host='jav888.com'),
    PROVIDER.site('Divine-DD', host='divine-dd.com'),
    PROVIDER.site('DownblouseJerk', host='downblousejerk.com'),
    PROVIDER.site('RealBikiniGirls', host='realbikinigirls.com'),
    PROVIDER.site('LingerieTales', host='lingerietales.com'),
    PROVIDER.site('POV Perv', host='tour.povperv.com'),
    PROVIDER.site('LegendaryX', host='legendaryx.com'),
    PROVIDER.site('Amazing Films', host='amazingfilms.com'),
    PROVIDER.site('Lucid Flix', host='lucidflix.com'),
    PROVIDER.site('Nick Marxx', host='nickmarxx.com'),
    PROVIDER.site('BlackBullChallenge', host='blackbullchallenge.com'),
    PROVIDER.site('Dark Shade', host='darkshade.com'),
    PROVIDER.site('Dick HD Daily', host='dickhddaily.com'),
    PROVIDER.site('Dire Desires', host='diredesires.com'),
    PROVIDER.site('Purity VR', host='purityvr.com'),
    PROVIDER.site('Passion POV', host='passionpov.com'),
    PROVIDER.site('Queer Crush', host='queercrush.com'),
    PROVIDER.site('Hard Werk', host='hardwerk.com'),
    PROVIDER.site('Cannon Prod', host='cannonprod.com'),
    PROVIDER.site('Bemefi', host='bemefi.com'),
    PROVIDER.site('FreakMobMedia', host='freakmobmedia.com'),
    PROVIDER.site('XFul', host='xful.com'),
    PROVIDER.site('S3XUS', host='s3xus.com'),
    PROVIDER.site('Yes Girlz', host='yesgirlz.com'),
    PROVIDER.site('Z Filmz Originals', host='z-filmz-originals.com'),
    PROVIDER.site('Hoby Buchanon', host='hobybuchanon.com'),
    PROVIDER.site('VRHush', host='vrhush.com'),
]
