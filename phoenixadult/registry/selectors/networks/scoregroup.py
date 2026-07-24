from __future__ import annotations

from phoenixadult.registry.selectors._factory import make_site
from phoenixadult.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'The Score Group'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''


def _site(name: str, host: str, video_list_path: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path=video_list_path,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='scoregroup',
    )


SCOREGROUP_SITES: list[SiteInfo] = [
    _site('Porn Mega Load', 'pornmegaload.com', '/hd-porn-scenes/'),
    _site('Naughty Mag', 'naughtymag.com', '/amateur-videos/'),
    _site('XL Girls', 'xlgirls.com', '/bbw-videos/'),
    _site('Bootylicious Mag', 'bootyliciousmag.com', '/big-booty-videos/'),
    _site('50 Plus MILFS', '50plusmilfs.com', '/xxx-milf-videos/'),
    _site('60 Plus MILFS', '60plusmilfs.com', '/xxx-granny-videos/'),
    _site('18 Eighteen', '18eighteen.com', '/xxx-teen-videos/'),
    _site('Big Boob Bundle', 'bigboobbundle.com', '/videos/'),
    _site('Leg Sex', 'legsex.com', '/foot-fetish-videos/'),
    _site('Scoreland', 'scoreland.com', '/big-boob-videos/'),
    _site('Christy Marks', 'christymarks.com', '/videos/'),
    _site('ScorelandTwo', 'scoreland2.com', '/big-boob-scenes/'),
    _site('ScoreVideos', 'scorevideos.com', '/porn-videos/'),
    _site('Score Classics', 'scoreclassics.com', '/classic-boob-videos/'),
]
