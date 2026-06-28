from __future__ import annotations

from app.registry.selectors._factory import make_site
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Naughty America'
PROVIDER_BASE_URL = 'https://www.naughtyamerica.com'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/search?term={query}'

_NAMES = [
    'My Friends Hot Mom',
    'My First Sex Teacher',
    'Seduced By A Cougar',
    'My Daughters Hot Friend',
    'My Wife is My Pornstar',
    'Tonights Girlfriend Classic',
    'Wives on Vacation',
    'My Sisters Hot Friend',
    'Naughty Weddings',
    'Dirty Wives Club',
    'My Dads Hot Girlfriend',
    'My Girl Loves Anal',
    'Lesbian Girl on Girl',
    'Naughty Office',
    'I have a Wife',
    'Naughty Bookworms',
    'Housewife 1 on 1',
    'My Wifes Hot Friend',
    'Latin Adultery',
    'Ass Masterpiece',
    '2 Chicks Same Time',
    'My Friends Hot Girl',
    'Neighbor Affair',
    'My Girlfriends Busty Friend',
    'Naughty Athletics',
    'My Naughty Massage',
    'Fast Times',
    'The Passenger',
    'Milf Sugar Babes',
    'Perfect Fucking Strangers',
    'Asian 1 on 1',
    'American Daydreams',
    'SoCal Coeds',
    'Naughty Country Girls',
    'Diary of a Milf',
    'Naughty Rich Girls',
    'My Naughty Latin Maid',
    'Naughty America',
    'Diary of a Nanny',
    'Naughty Flipside',
    'Live Party Girl',
    'Live Naughty Student',
    'Live Naughty Secretary',
    'Live Gym Cam',
    'Live Naughty Teacher',
    'Live Naughty Milf',
    'Live Naughty Nurse',
    'Big Cock Bully',
    'LA Sluts',
    'Slut Stepsister',
    'Teens Love Cream',
    'Latina Stepmom',
    'Anal College',
    'Watch Your Wife',
    'Slut Stepmom',
    'Sleazy Stepdad',
    'Open Family',
    'Watch Your Mom',
    'Show My BF',
    'Big Cock Hero',
    "Mom's Money",
    'College Sugarbabes',
    'Mrs. Creampie',
    'Thundercock',
]


def _site(name: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=PROVIDER_BASE_URL,
        search_path=PROVIDER_SEARCH_PATH,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='naughtyamerica',
    )


NAUGHTYAMERICA_SITES: list[SiteInfo] = [_site(n) for n in _NAMES]
