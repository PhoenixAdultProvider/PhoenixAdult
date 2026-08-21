from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site

PROVIDER_NAME = 'Wankz'
PROVIDER_BASE_URL = 'https://wankz.com'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = ''

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


def _site(name: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=PROVIDER_BASE_URL,
        search_path='/search?q={query}',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='wankz',
    )


SITES: list[SiteInfo] = [_site(n) for n in _NAMES]
