from __future__ import annotations

from dataclasses import replace

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'FuckYouCash'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = 'Title only — must match the slug in the scene URL'
PROVIDER_SEARCH_PATH = ''
PROVIDER_DATA18_ENRICHMENT = True

PROVIDER = Provider.from_headers(__name__)

PORN_PROS = 'Porn Pros'
PORN_PLUS = 'Porn+'


def _group(sub_group: str, sites: list[SiteInfo]) -> list[SiteInfo]:
    return [replace(site, sub_group=sub_group) for site in sites]


PORN_PROS_SITES = [
    PROVIDER.site('18 Years Old', host='pornpros.com'),
    PROVIDER.site('40oz Bounce', host='pornpros.com'),
    PROVIDER.site('Cock Competition', host='pornpros.com'),
    PROVIDER.site('Cruelty Party', host='pornpros.com'),
    PROVIDER.site('Cum Disgrace', host='pornpros.com'),
    PROVIDER.site('Cumshot Surprise', host='pornpros.com'),
    PROVIDER.site('Deep Throat Love', host='pornpros.com'),
    PROVIDER.site('Disgraced 18', host='pornpros.com'),
    PROVIDER.site('Euro Humpers', host='pornpros.com'),
    PROVIDER.site('Flexible Positions', host='pornpros.com'),
    PROVIDER.site('Freaks of Boobs', host='pornpros.com'),
    PROVIDER.site('Freaks of Cock', host='pornpros.com'),
    PROVIDER.site('Jurassic Cock', host='pornpros.com'),
    PROVIDER.site('Massage Creep', host='pornpros.com'),
    PROVIDER.site('MILF Humiliation', host='pornpros.com', data18_enrichment=False),
    PROVIDER.site('Pimp Parade', host='pornpros.com'),
    PROVIDER.site('Porn Pros', host='pornpros.com'),
    PROVIDER.site('Public Violations', host='pornpros.com'),
    PROVIDER.site('Real Ex-Girlfriends', host='pornpros.com'),
    PROVIDER.site('Shady Pi', host='pornpros.com'),
    PROVIDER.site('Squirt Disgrace', host='pornpros.com'),
    PROVIDER.site('TeenBFF', host='pornpros.com'),
]

PORN_PLUS_SITES = [
    PROVIDER.site('Asians Exploited', host='pornplus.com'),
    PROVIDER.site('BBC POVD', host='pornplus.com'),
    PROVIDER.site('Bikini Smash', host='pornplus.com', data18_enrichment=False),
    PROVIDER.site('Boobs4K', host='pornplus.com', data18_enrichment=False),
    PROVIDER.site('Caged Sex', host='pornplus.com'),
    PROVIDER.site('Creepy PA', host='pornplus.com', fallback_url='https://creepypa.com', data18_enrichment=False),
    PROVIDER.site('Double Trouble', host='pornplus.com'),
    PROVIDER.site('Exploited Cheerleaders', host='pornplus.com', data18_enrichment=False),
    PROVIDER.site('Facials Galore', host='pornplus.com'),
    PROVIDER.site('Game On', host='pornplus.com'),
    PROVIDER.site('Girl Scout Sex', host='pornplus.com', data18_enrichment=False),
    PROVIDER.site('Glory Hole 4K', host='pornplus.com'),
    PROVIDER.site('Kinky Sluts 4K', host='pornplus.com', fallback_url='https://kinkysluts4k.org'),
    PROVIDER.site('MomCum', host='pornplus.com', fallback_url='https://momcum.com'),
    PROVIDER.site('Passion Fuck', host='pornplus.com'),
    PROVIDER.site('Penis to Pussy', host='pornplus.com'),
    PROVIDER.site('Porn+', host='pornplus.com'),
    PROVIDER.site('Pornstars in Cars', host='pornplus.com'),
    PROVIDER.site('Public Pickup', host='pornplus.com'),
    PROVIDER.site('Property Exploits', host='pornplus.com'),
    PROVIDER.site('RV Adventures', host='pornplus.com'),
    PROVIDER.site('School of Cock', host='pornplus.com'),
    PROVIDER.site('Sexercise', host='pornplus.com'),
    PROVIDER.site('Shower 4K', host='pornplus.com'),
    PROVIDER.site('Squirt Bomb', host='pornplus.com'),
    PROVIDER.site('Strip Club Tryouts', host='pornplus.com'),
    PROVIDER.site('Throat Creampies', host='pornplus.com'),
    PROVIDER.site('Waxxxed', host='pornplus.com'),
    PROVIDER.site('Zoom POV', host='pornplus.com'),
]

STANDALONE_SITES = [
    PROVIDER.site('Anal4K', host='anal4k.com'),
    PROVIDER.site('BAEB', host='baeb.com'),
    PROVIDER.site('BBC Pie', host='bbcpie.com'),
    PROVIDER.site('Casting Couch-X', host='castingcouch-x.com'),
    PROVIDER.site('Cum4K', host='cum4k.com'),
    PROVIDER.site('Exotic4K', host='exotic4k.com'),
    PROVIDER.site('Facials4K', host='facials4k.com'),
    PROVIDER.site('FantasyHD', host='fantasyhd.com'),
    PROVIDER.site('Girl Cum', host='girlcum.com'),
    PROVIDER.site('Holed', host='holed.com'),
    PROVIDER.site('Lubed', host='lubed.com'),
    PROVIDER.site('Mom4K', host='mom4k.com'),
    PROVIDER.site('My Very First Time', host='myveryfirsttime.com'),
    PROVIDER.site('Nanny Spy', host='nannyspy.com'),
    PROVIDER.site('Passion-HD', host='passion-hd.com'),
    PROVIDER.site('POVD', host='povd.com'),
    PROVIDER.site('Pure Mature', host='puremature.com'),
    PROVIDER.site('Spy Fam', host='spyfam.com'),
    PROVIDER.site('Strippers 4K', host='strippers4k.com'),
    PROVIDER.site('Tiny4K', host='tiny4k.com'),
    PROVIDER.site('WetVR', host='wetvr.com'),
]

SITES: list[SiteInfo] = [
    *_group(PORN_PROS, PORN_PROS_SITES),
    *_group(PORN_PLUS, PORN_PLUS_SITES),
    *STANDALONE_SITES,
]
