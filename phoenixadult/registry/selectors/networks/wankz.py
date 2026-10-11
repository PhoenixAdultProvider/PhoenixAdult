from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Wankz'
PROVIDER_BASE_URL = 'https://wankz.com'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/search?q={query}'

_NAMES = [
    '4K Desire',
    'All Interracial',
    'Bang My Stepmom',
    'Big Tits Like Big Dicks',
    'Bubbly Massage',
    'Cougar Sex Club',
    'Ebony Internal',
    'Escort Trick',
    'Exploited 18',
    'Handjob Harry',
    'I Am Eighteen',
    'Lesbian Sistas',
    'Make Them Gag',
    'My MILF Boss',
    'Not So Innocent Teens',
    'Rap Video Auditions',
    'Real Blowjob Auditions',
    'Round Juicy Butts',
    'Schoolgirl Internal',
    'Service Whores',
    'Sex for Grades',
    'Spoiled Slut',
    'Swallow for Cash',
    'Tight Holes Big Poles',
    'Wank My Wood',
    'Wankz TV',
    'Whale Tailn',
    'Wild Massage',
    'XXX at Work',
    'Young Dirty Lesbians',
    'Young Sluts Hardcore',
    'Matrix Models',
    'Blow Patrol',
]

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [PROVIDER.site(n) for n in _NAMES]
