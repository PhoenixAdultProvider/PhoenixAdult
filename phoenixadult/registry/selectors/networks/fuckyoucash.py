from __future__ import annotations

from dataclasses import replace

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site

PROVIDER_NAME = 'FuckYouCash'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = 'Title only — must match the slug in the scene URL'
PORN_PROS = 'Porn Pros'
PORN_PLUS = 'Porn+'


def _site(name: str, host: str, fallback: str = '', data18: bool = True) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        fallback_url=f'https://{fallback}' if fallback else '',
        search_path='',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='fuckyoucash',
        data18_enrichment=data18,
    )


def _group(sub_group: str, sites: list[SiteInfo]) -> list[SiteInfo]:
    return [replace(site, sub_group=sub_group) for site in sites]


PORN_PROS_SITES = [
    _site('18 Years Old', 'pornpros.com'),
    _site('40oz Bounce', 'pornpros.com'),
    _site('Cock Competition', 'pornpros.com'),
    _site('Cruelty Party', 'pornpros.com'),
    _site('Cum Disgrace', 'pornpros.com'),
    _site('Cumshot Surprise', 'pornpros.com'),
    _site('Deep Throat Love', 'pornpros.com'),
    _site('Disgraced 18', 'pornpros.com'),
    _site('Euro Humpers', 'pornpros.com'),
    _site('Flexible Positions', 'pornpros.com'),
    _site('Freaks of Boobs', 'pornpros.com'),
    _site('Freaks of Cock', 'pornpros.com'),
    _site('Jurassic Cock', 'pornpros.com'),
    _site('Massage Creep', 'pornpros.com'),
    _site('MILF Humiliation', 'pornpros.com', data18=False),
    _site('Pimp Parade', 'pornpros.com'),
    _site('Porn Pros', 'pornpros.com'),
    _site('Public Violations', 'pornpros.com'),
    _site('Real Ex-Girlfriends', 'pornpros.com'),
    _site('Shady Pi', 'pornpros.com'),
    _site('Squirt Disgrace', 'pornpros.com'),
    _site('TeenBFF', 'pornpros.com'),
]

PORN_PLUS_SITES = [
    _site('Asians Exploited', 'pornplus.com'),
    _site('BBC POVD', 'pornplus.com'),
    _site('Bikini Smash', 'pornplus.com', data18=False),
    _site('Boobs4K', 'pornplus.com', data18=False),
    _site('Caged Sex', 'pornplus.com'),
    _site('Creepy PA', 'pornplus.com', fallback='creepypa.com', data18=False),
    _site('Double Trouble', 'pornplus.com'),
    _site('Exploited Cheerleaders', 'pornplus.com', data18=False),
    _site('Facials Galore', 'pornplus.com'),
    _site('Game On', 'pornplus.com'),
    _site('Girl Scout Sex', 'pornplus.com', data18=False),
    _site('Glory Hole 4K', 'pornplus.com'),
    _site('Kinky Sluts 4K', 'pornplus.com', fallback='kinkysluts4k.org'),
    _site('MomCum', 'pornplus.com', fallback='momcum.com'),
    _site('Passion Fuck', 'pornplus.com'),
    _site('Penis to Pussy', 'pornplus.com'),
    _site('Porn+', 'pornplus.com'),
    _site('Pornstars in Cars', 'pornplus.com'),
    _site('Public Pickup', 'pornplus.com'),
    _site('Property Exploits', 'pornplus.com'),
    _site('RV Adventures', 'pornplus.com'),
    _site('School of Cock', 'pornplus.com'),
    _site('Sexercise', 'pornplus.com'),
    _site('Shower 4K', 'pornplus.com'),
    _site('Squirt Bomb', 'pornplus.com'),
    _site('Strip Club Tryouts', 'pornplus.com'),
    _site('Throat Creampies', 'pornplus.com'),
    _site('Waxxxed', 'pornplus.com'),
    _site('Zoom POV', 'pornplus.com'),
]

STANDALONE_SITES = [
    _site('Anal4K', 'anal4k.com'),
    _site('BAEB', 'baeb.com'),
    _site('BBC Pie', 'bbcpie.com'),
    _site('Casting Couch-X', 'castingcouch-x.com'),
    _site('Cum4K', 'cum4k.com'),
    _site('Exotic4K', 'exotic4k.com'),
    _site('Facials4K', 'facials4k.com'),
    _site('FantasyHD', 'fantasyhd.com'),
    _site('Girl Cum', 'girlcum.com'),
    _site('Holed', 'holed.com'),
    _site('Lubed', 'lubed.com'),
    _site('Mom4K', 'mom4k.com'),
    _site('My Very First Time', 'myveryfirsttime.com'),
    _site('Nanny Spy', 'nannyspy.com'),
    _site('Passion-HD', 'passion-hd.com'),
    _site('POVD', 'povd.com'),
    _site('Pure Mature', 'puremature.com'),
    _site('Spy Fam', 'spyfam.com'),
    _site('Strippers 4K', 'strippers4k.com'),
    _site('Tiny4K', 'tiny4k.com'),
    _site('WetVR', 'wetvr.com'),
]

SITES: list[SiteInfo] = [
    *_group(PORN_PROS, PORN_PROS_SITES),
    *_group(PORN_PLUS, PORN_PLUS_SITES),
    *STANDALONE_SITES,
]
