from __future__ import annotations

from phoenixadult.models.site_info import BypassName, ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'The Score Group'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_BYPASS: list[BypassName] = ['Impersonate', 'FlareSolverr']
PROVIDER_DATA18_ENRICHMENT = True

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Porn Mega Load', host='www.pornmegaload.com', search_path='/hd-porn-scenes/'),
    PROVIDER.site('Naughty Mag', host='www.naughtymag.com', search_path='/amateur-videos/'),
    PROVIDER.site('XL Girls', host='www.xlgirls.com', search_path='/bbw-videos/'),
    PROVIDER.site('Bootylicious Mag', host='www.bootyliciousmag.com', search_path='/big-booty-videos/'),
    PROVIDER.site('50 Plus MILFs', host='www.50plusmilfs.com', search_path='/xxx-milf-videos/'),
    PROVIDER.site('60 Plus MILFs', host='www.60plusmilfs.com', search_path='/xxx-granny-videos/'),
    PROVIDER.site('18 Eighteen', host='www.18eighteen.com', search_path='/xxx-teen-videos/'),
    PROVIDER.site('Big Boob Bundle', host='www.bigboobbundle.com', search_path='/videos/'),
    PROVIDER.site('Leg Sex', host='www.legsex.com', search_path='/foot-fetish-videos/'),
    PROVIDER.site('Scoreland', host='www.scoreland.com', search_path='/big-boob-videos/'),
    PROVIDER.site('Christy Marks', host='www.christymarks.com', search_path='/videos/'),
    PROVIDER.site('ScorelandTwo', host='www.scoreland2.com', search_path='/big-boob-scenes/'),
    PROVIDER.site('ScoreVideos', host='www.scorevideos.com', search_path='/porn-videos/'),
    PROVIDER.site('Score Classics', host='www.scoreclassics.com', search_path='/classic-boob-videos/'),
]
